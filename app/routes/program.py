from flask import render_template, redirect, url_for, flash, request, Blueprint, session as flask_session
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from app import db
from app.models import WorkoutTemplate, WorkoutSchedule, TemplateExercise, WorkoutSession, SetLog, Exercise
from app.forms import ProgramGenerationForm, ExerciseParametersForm
import json

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
        # ... существующий код обработки POST (без изменений) ...
        all_valid = True
        parameters = {}
        
        for te in template_exercises:
            exercise_type = te.exercise.exercise_type
            
            if exercise_type == 'cardio':
                duration = request.form.get(f'duration_{te.id}', type=int)
                distance = request.form.get(f'distance_{te.id}', type=float)
                heart_rate = request.form.get(f'heart_rate_{te.id}', type=int)
                
                if not duration:
                    duration = 30
                if not distance:
                    distance = 0
                
                parameters[str(te.exercise_id)] = {
                    'input_type': 'cardio',
                    'duration': duration,
                    'distance': distance,
                    'target_heart_rate': heart_rate,
                    'exercise_name': te.exercise.name,
                    'exercise_type': 'cardio'
                }
                
            elif exercise_type == 'bodyweight':
                input_type = request.form.get(f'ex_{te.id}-input_type')
                
                if input_type == 'fixed':
                    sets = int(request.form.get(f'ex_{te.id}-sets', 3))
                    reps = int(request.form.get(f'ex_{te.id}-reps', 10))
                    
                    parameters[str(te.exercise_id)] = {
                        'input_type': 'fixed',
                        'sets': sets,
                        'reps': reps,
                        'weight': 0,
                        'exercise_name': te.exercise.name,
                        'exercise_type': 'bodyweight'
                    }
                else:
                    progressive_data_json = request.form.get(f'progressive_data_{te.id}')
                    if progressive_data_json:
                        try:
                            progressive_sets = json.loads(progressive_data_json)
                            if not progressive_sets:
                                flash(f'Для упражнения "{te.exercise.name}" не добавлено ни одного подхода', 'danger')
                                all_valid = False
                                continue
                            
                            for set_info in progressive_sets:
                                set_info['weight'] = 0
                            
                            parameters[str(te.exercise_id)] = {
                                'input_type': 'progressive',
                                'sets': progressive_sets,
                                'exercise_name': te.exercise.name,
                                'exercise_type': 'bodyweight'
                            }
                        except json.JSONDecodeError:
                            flash(f'Ошибка в данных упражнения "{te.exercise.name}"', 'danger')
                            all_valid = False
                            continue
                    else:
                        flash(f'Для упражнения "{te.exercise.name}" не заполнены параметры', 'danger')
                        all_valid = False
                        continue
                        
            else:  # strength
                input_type = request.form.get(f'ex_{te.id}-input_type')
                
                if input_type == 'fixed':
                    sets = int(request.form.get(f'ex_{te.id}-sets', 3))
                    reps = int(request.form.get(f'ex_{te.id}-reps', 10))
                    weight = float(request.form.get(f'ex_{te.id}-weight', 0))
                    
                    parameters[str(te.exercise_id)] = {
                        'input_type': 'fixed',
                        'sets': sets,
                        'reps': reps,
                        'weight': weight,
                        'exercise_name': te.exercise.name,
                        'exercise_type': 'strength'
                    }
                else:
                    progressive_data_json = request.form.get(f'progressive_data_{te.id}')
                    if progressive_data_json:
                        try:
                            progressive_sets = json.loads(progressive_data_json)
                            if not progressive_sets:
                                flash(f'Для упражнения "{te.exercise.name}" не добавлено ни одного подхода', 'danger')
                                all_valid = False
                                continue
                            
                            parameters[str(te.exercise_id)] = {
                                'input_type': 'progressive',
                                'sets': progressive_sets,
                                'exercise_name': te.exercise.name,
                                'exercise_type': 'strength'
                            }
                        except json.JSONDecodeError:
                            flash(f'Ошибка в данных упражнения "{te.exercise.name}"', 'danger')
                            all_valid = False
                            continue
                    else:
                        flash(f'Для упражнения "{te.exercise.name}" не заполнены параметры', 'danger')
                        all_valid = False
                        continue
        
        if all_valid:
            # Генерируем расписание
            start_date = datetime.strptime(program_data['start_date'], '%Y-%m-%d').date()
            end_date = datetime.strptime(program_data['end_date'], '%Y-%m-%d').date()
            
            days_map = {
                'monday': 0, 'tuesday': 1, 'wednesday': 2,
                'thursday': 3, 'friday': 4, 'saturday': 5, 'sunday': 6
            }
            
            selected_weekdays = [days_map[day] for day in program_data['days']]
            
            current_date = start_date
            schedules_created = 0
            
            while current_date <= end_date:
                if current_date.weekday() in selected_weekdays:
                    schedule = WorkoutSchedule(
                        user_id=current_user.id,
                        template_id=program_data['template_id'],
                        scheduled_date=current_date,
                        planned_data=parameters,
                        status='planned'
                    )
                    db.session.add(schedule)
                    schedules_created += 1
                current_date += timedelta(days=1)
            
            db.session.commit()
            
            flask_session.pop('program_data', None)
            
            flash(f'Программа успешно создана! Сгенерировано {schedules_created} тренировок.', 'success')
            return redirect(url_for('main.dashboard'))
    
    return render_template('program/set_parameters.html', 
                         template=template, 
                         template_exercises=template_exercises, 
                         forms=forms,
                         last_data=last_data)

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