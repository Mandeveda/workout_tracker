from flask import render_template, redirect, url_for, flash, request, Blueprint, session as flask_session
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from app import db
from app.models import WorkoutTemplate, WorkoutSchedule, TemplateExercise, WorkoutSession, SetLog, Exercise
from app.forms import ProgramGenerationForm, ExerciseParametersForm
import json
from app.textutil import plural

bp = Blueprint('program', __name__, url_prefix='/program')

@bp.route('/create/<int:template_id>', methods=['GET', 'POST'])
@login_required
def create_program(template_id):
    """Шаг 1: Выбор дней недели и периода"""
    template = WorkoutTemplate.query.get_or_404(template_id)
    
    if template.user_id != current_user.id:
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('templates.list_templates'))
    
    form = ProgramGenerationForm()
    form.template_id.choices = [(template.id, template.name)]  # Фиксируем выбор
    
    if form.validate_on_submit():
        # Сохраняем данные в сессию для следующего шага
        flask_session['program_data'] = {
            'template_id': form.template_id.data,
            'days': [
                day for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                if getattr(form, day).data
            ],
            'start_date': form.start_date.data.strftime('%Y-%m-%d'),
            'end_date': form.end_date.data.strftime('%Y-%m-%d')
        }
        return redirect(url_for('program.set_parameters'))
    
    return render_template('program/create.html', form=form, template=template)

@bp.route('/set_parameters', methods=['GET', 'POST'])
@login_required
def set_parameters():
    """Шаг 2: Заполнение параметров для каждого упражнения"""
    if 'program_data' not in flask_session:
        flash('Сначала выберите параметры программы', 'warning')
        return redirect(url_for('templates.list_templates'))
    
    program_data = flask_session['program_data']
    template = WorkoutTemplate.query.get_or_404(program_data['template_id'])
    
    # Получаем упражнения из шаблона
    template_exercises = TemplateExercise.query.filter_by(template_id=template.id).order_by(TemplateExercise.order).all()
    
    # Создаём форму для каждого упражнения
    forms = {}
    last_data = {}  # Храним последние данные по каждому упражнению
    
    for te in template_exercises:
        forms[te.id] = ExerciseParametersForm(prefix=f'ex_{te.id}')
        
        # Получаем последние данные по этому упражнению
        last = get_last_workout_data(current_user.id, te.exercise_id)
        if last:
            last_data[te.id] = last
    
    if request.method == 'POST':
        parameters, problems = {}, []
        for te in template_exercises:
            plan, problem = parse_exercise_plan(te, request.form)
            if problem:
                problems.append(f'Проверьте «{te.exercise.name}»: {problem}')
            else:
                parameters[str(te.exercise_id)] = plan
        
        if problems:
            for problem in problems:
                flash(problem, 'danger')
        else:
            start_date = datetime.strptime(program_data['start_date'], '%Y-%m-%d').date()
            end_date = datetime.strptime(program_data['end_date'], '%Y-%m-%d').date()
            days_map = {'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                        'friday': 4, 'saturday': 5, 'sunday': 6}
            selected_weekdays = {days_map[day] for day in program_data['days']}
            
            # Даты, на которые этот шаблон уже стоит в расписании, не дублируем
            taken = {s.scheduled_date for s in WorkoutSchedule.query.filter(
                WorkoutSchedule.user_id == current_user.id,
                WorkoutSchedule.template_id == template.id,
                WorkoutSchedule.scheduled_date.between(start_date, end_date)
            )}
            created = skipped = 0
            current_date = start_date
            while current_date <= end_date:
                if current_date.weekday() in selected_weekdays:
                    if current_date in taken:
                        skipped += 1
                    else:
                        db.session.add(WorkoutSchedule(
                            user_id=current_user.id,
                            template_id=template.id,
                            scheduled_date=current_date,
                            planned_data=parameters,
                            status='planned'
                        ))
                        created += 1
                current_date += timedelta(days=1)
            db.session.commit()
            flask_session.pop('program_data', None)
            
            message = f'Расписание готово: {created} {plural(created, "тренировка", "тренировки", "тренировок")}.'
            if skipped:
                message += f' {skipped} — на даты, где «{template.name}» уже стоял в расписании, — пропущено.'
            flash(message, 'success')
            return redirect(url_for('main.dashboard'))
    
    return render_template('program/set_parameters.html', 
                         template=template, 
                         template_exercises=template_exercises, 
                         forms=forms,
                         last_data=last_data)

# Допустимые значения в плане: (минимум, максимум)
LIMITS = {'sets': (1, 20), 'reps': (1, 1000), 'weight': (0, 1000),
          'duration': (1, 600), 'distance': (0, 500), 'heart_rate': (40, 220)}


def parse_number(value, kind, cast=int):
    """Число из поля формы в допустимых пределах или None (пусто, не число, вне пределов)"""
    try:
        number = cast(str(value).strip().replace(',', '.'))
    except (TypeError, ValueError):
        return None
    low, high = LIMITS[kind]
    return number if low <= number <= high else None


def parse_exercise_plan(te, form):
    """План одного упражнения из формы шага 2: (план, None) или (None, текст ошибки)"""
    ex_type = te.exercise.exercise_type
    base = {'exercise_name': te.exercise.name, 'exercise_type': ex_type}
    
    if ex_type == 'cardio':
        duration = parse_number(form.get(f'duration_{te.id}') or 30, 'duration')
        distance = parse_number(form.get(f'distance_{te.id}') or 0, 'distance', float)
        heart_raw = form.get(f'heart_rate_{te.id}')
        heart_rate = parse_number(heart_raw, 'heart_rate') if heart_raw else None
        if duration is None:
            return None, 'длительность — от 1 до 600 минут'
        if distance is None:
            return None, 'дистанция — от 0 до 500 км'
        if heart_raw and heart_rate is None:
            return None, 'пульс — от 40 до 220 уд/мин'
        return {'input_type': 'cardio', 'duration': duration, 'distance': distance,
                'target_heart_rate': heart_rate, **base}, None
    
    with_weight = ex_type == 'strength'
    if form.get(f'ex_{te.id}-input_type') == 'progressive':
        try:
            raw_sets = json.loads(form.get(f'progressive_data_{te.id}') or '')
        except ValueError:
            return None, 'не удалось прочитать подходы — заполните их заново'
        if not isinstance(raw_sets, list) or not 1 <= len(raw_sets) <= LIMITS['sets'][1]:
            return None, 'нужен хотя бы один подход (не больше 20)'
        sets = []
        for n, item in enumerate(raw_sets, start=1):
            reps = parse_number(item.get('reps') if isinstance(item, dict) else None, 'reps')
            weight = parse_number(item.get('weight', 0), 'weight', float) if with_weight and isinstance(item, dict) else 0
            if reps is None or weight is None:
                return None, f'подход {n}: повторения — от 1 до 1000, вес — от 0 до 1000 кг'
            sets.append({'set_number': n, 'reps': reps, 'weight': weight})
        return {'input_type': 'progressive', 'sets': sets, **base}, None
    
    sets = parse_number(form.get(f'ex_{te.id}-sets'), 'sets')
    reps = parse_number(form.get(f'ex_{te.id}-reps'), 'reps')
    weight = parse_number(form.get(f'ex_{te.id}-weight', 0), 'weight', float) if with_weight else 0
    if sets is None:
        return None, 'подходов — от 1 до 20'
    if reps is None:
        return None, 'повторений — от 1 до 1000'
    if weight is None:
        return None, 'вес — от 0 до 1000 кг'
    return {'input_type': 'fixed', 'sets': sets, 'reps': reps, 'weight': weight, **base}, None


def get_last_workout_data(user_id, exercise_id):
    """
    Возвращает последние фактические данные по упражнению для пользователя.
    Возвращает словарь с ключами: weight, reps, sets (если есть)
    """
    # Ищем последний выполненный подход по этому упражнению
    last_log = SetLog.query.join(WorkoutSession).filter(
        WorkoutSession.user_id == user_id,
        SetLog.exercise_id == exercise_id,
        SetLog.actual_weight.isnot(None),
        SetLog.actual_reps.isnot(None)
    ).order_by(WorkoutSession.date.desc(), SetLog.set_number.desc()).first()
    
    if last_log:
        return {
            'weight': last_log.actual_weight,
            'reps': last_log.actual_reps,
            'date': last_log.session.date
        }
    
    # Если нет данных — ищем плановые данные из последней программы
    last_schedule = WorkoutSchedule.query.filter(
        WorkoutSchedule.user_id == user_id,
        WorkoutSchedule.planned_data.isnot(None)
    ).order_by(WorkoutSchedule.scheduled_date.desc()).first()
    
    if last_schedule and last_schedule.planned_data:
        planned = last_schedule.planned_data.get(str(exercise_id))
        if planned:
            if planned.get('input_type') == 'fixed':
                return {
                    'weight': planned.get('weight', 0),
                    'reps': planned.get('reps', 0),
                    'date': last_schedule.scheduled_date
                }
            elif planned.get('input_type') == 'progressive' and planned.get('sets'):
                last_set = planned['sets'][-1]
                return {
                    'weight': last_set.get('weight', 0),
                    'reps': last_set.get('reps', 0),
                    'date': last_schedule.scheduled_date
                }
    
    return None