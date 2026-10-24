from flask import render_template, redirect, url_for, flash, request, Blueprint, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime
from app import db, limiter
from app.models import WorkoutSchedule, WorkoutSession, SetLog, Exercise, TemplateExercise
from app.routes.main import session_title, human_date, MONTHS_SHORT
from app.timeutil import local_today, local_date

bp = Blueprint('workouts', __name__, url_prefix='/workouts')


@bp.route('/')
@login_required
def index():
    """Список тренировок на сегодня и предстоящие"""
    today = local_today()
    
    # Активные (незавершённые) тренировки
    active_sessions = WorkoutSession.query.filter_by(
        user_id=current_user.id,
        is_completed=False  # Добавим поле is_completed в модель
    ).order_by(WorkoutSession.date.desc()).all()
    
    # Тренировки на сегодня
    today_workouts = WorkoutSchedule.query.filter_by(
        user_id=current_user.id,
        scheduled_date=today,
        status='planned'
    ).all()
    
    # Пропущенные: запланированы на прошедшие дни, но не начаты и не отмечены пропуском
    overdue = WorkoutSchedule.query.filter(
        WorkoutSchedule.user_id == current_user.id,
        WorkoutSchedule.scheduled_date < today,
        WorkoutSchedule.status == 'planned'
    ).order_by(WorkoutSchedule.scheduled_date.desc()).limit(10).all()
    
    # Предстоящие тренировки (следующие 7 дней)
    upcoming = WorkoutSchedule.query.filter(
        WorkoutSchedule.user_id == current_user.id,
        WorkoutSchedule.scheduled_date > today,
        WorkoutSchedule.status == 'planned'
    ).order_by(WorkoutSchedule.scheduled_date).limit(10).all()
    
    # История последних тренировок
    history = WorkoutSession.query.filter_by(
        user_id=current_user.id,
        is_completed=True
    ).order_by(WorkoutSession.date.desc()).limit(10).all()
    
    return render_template('workouts/index.html', 
                         active_sessions=active_sessions,
                         today_workouts=today_workouts,
                         overdue=overdue,
                         today=today,
                         upcoming=upcoming,
                         history=history,
                         session_title=session_title,
                         human_date=human_date,
                         months_short=MONTHS_SHORT)

@bp.route('/start')
@bp.route('/start/<int:schedule_id>')
@login_required
def start_workout(schedule_id=None):
    """Начать тренировку"""
    today = local_today()
    
    if schedule_id is None:
        schedule = WorkoutSchedule.query.filter_by(
            user_id=current_user.id,
            scheduled_date=today,
            status='planned'
        ).first()
        
        if not schedule:
            flash('Нет запланированных тренировок на сегодня', 'warning')
            return redirect(url_for('workouts.index'))
    else:
        schedule = WorkoutSchedule.query.get_or_404(schedule_id)
        
        if schedule.user_id != current_user.id:
            flash('Доступ запрещён', 'danger')
            return redirect(url_for('workouts.index'))
        
        if schedule.scheduled_date != today:
            flash('Можно выполнять только тренировки, запланированные на сегодня', 'warning')
            return redirect(url_for('workouts.index'))
    
    if schedule.status != 'planned':
        flash('Эта тренировка уже выполнена или пропущена', 'warning')
        return redirect(url_for('workouts.index'))
    
    # Проверяем, есть ли уже активная сессия для этого расписания
    existing_session = WorkoutSession.query.filter_by(
        schedule_id=schedule.id, 
        is_completed=False
    ).first()
    
    if existing_session:
        flash('Тренировка уже была начата. Продолжите выполнение.', 'info')
        return redirect(url_for('workouts.perform', session_id=existing_session.id))
    
    # Создаём новую сессию (незавершённую)
    session = WorkoutSession(
        user_id=current_user.id,
        schedule_id=schedule.id,
        template_id=schedule.template_id,
        template_name=schedule.template.name,
        date=datetime.utcnow(),
        status='in_progress',  # Новый статус
        is_completed=False      # Новое поле
    )
    db.session.add(session)
    db.session.commit()
    
    flash('Тренировка начата! Заполните результаты подходов.', 'success')
    return redirect(url_for('workouts.perform', session_id=session.id))

def planned_sets(schedule):
    """Запланированные подходы тренировки по порядку упражнений шаблона.

    Возвращает (упражнение шаблона, номер подхода, план повторений/минут, план веса/км).
    Учитываются упражнения, которые есть и в шаблоне, и в плане. Кардио — один «подход».
    """
    planned_data = schedule.planned_data or {}
    template_exercises = TemplateExercise.query.filter_by(
        template_id=schedule.template_id
    ).order_by(TemplateExercise.order).all()
    for te in template_exercises:
        plan = planned_data.get(str(te.exercise_id))
        if not plan:
            continue
        if te.exercise.exercise_type == 'cardio':
            yield te, 1, plan.get('duration', 30), plan.get('distance', 0)
        elif plan.get('input_type') == 'progressive':
            for set_info in plan.get('sets', []):
                yield te, set_info['set_number'], set_info['reps'], set_info.get('weight', 0)
        else:
            for n in range(1, int(plan.get('sets', 0)) + 1):
                yield te, n, plan['reps'], plan.get('weight', 0)


def _blank(value):
    """Значение поля для шаблона: None → '', 0 остаётся 0"""
    return '' if value is None else value


@bp.route('/perform/<int:session_id>')
@login_required
def perform(session_id):
    """Экран выполнения тренировки по плану. Сохранение — через save_progress (фоном)"""
    session = WorkoutSession.query.get_or_404(session_id)
    
    if session.user_id != current_user.id:
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('workouts.index'))
    if session.is_completed:
        flash('Эта тренировка уже завершена', 'info')
        return redirect(url_for('workouts.summary', session_id=session.id))
    if not session.schedule:
        # Сессия без расписания — это свободная тренировка
        return redirect(url_for('workouts.free_workout', session_id=session.id))
    
    saved = {(log.exercise_id, log.set_number): log for log in SetLog.query.filter_by(session_id=session.id)}
    planned_data = session.schedule.planned_data or {}
    
    exercises_data, by_te = [], {}
    for te, set_number, plan_a, plan_b in planned_sets(session.schedule):
        log = saved.get((te.exercise_id, set_number))
        if te.id not in by_te:
            by_te[te.id] = {
                'template_exercise_id': te.id,
                'exercise_id': te.exercise_id,
                'exercise_name': te.exercise.name,
                'exercise_type': te.exercise.exercise_type,
                'sets': [],
            }
            exercises_data.append(by_te[te.id])
        item = by_te[te.id]
        if item['exercise_type'] == 'cardio':
            item.update({
                'planned_duration': plan_a,
                'planned_distance': plan_b,
                'planned_heart_rate': planned_data.get(str(te.exercise_id), {}).get('target_heart_rate'),
                'actual_duration': _blank(log.actual_reps) if log else '',
                'actual_distance': _blank(log.actual_weight) if log else '',
            })
        else:
            item['sets'].append({
                'set_number': set_number,
                'planned_reps': plan_a,
                'planned_weight': plan_b,
                'actual_reps': _blank(log.actual_reps) if log else '',
                'actual_weight': _blank(log.actual_weight) if log else '',
            })
    
    # Последний результат по каждому упражнению из прошлых завершённых тренировок
    for exercise in exercises_data:
        last_log = SetLog.query.join(WorkoutSession).filter(
            WorkoutSession.user_id == current_user.id,
            WorkoutSession.id != session.id,
            WorkoutSession.is_completed.is_(True),
            SetLog.exercise_id == exercise['exercise_id'],
            SetLog.actual_reps.isnot(None)
        ).order_by(WorkoutSession.date.desc(), SetLog.set_number).first()
        exercise['prev'] = {'weight': last_log.actual_weight, 'reps': last_log.actual_reps} if last_log else None
    
    return render_template('workouts/perform.html', session=session, exercises_data=exercises_data)


@bp.route('/save_progress/<int:session_id>', methods=['POST'])
@limiter.exempt  # AJAX-автосохранение не должно упираться в общий лимит
@login_required
def save_progress(session_id):
    """Сохранение отмеченных подходов тренировки по плану (AJAX).

    Приходят только отмеченные подходы. Подход из запроса создаётся или обновляется,
    сохранённый подход, которого в запросе нет (отметку сняли), удаляется.
    """
    session = WorkoutSession.query.get_or_404(session_id)
    if session.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    if session.is_completed:
        return jsonify({'success': False, 'error': 'Training already completed'}), 400
    if not session.schedule:
        return jsonify({'success': False, 'error': 'Schedule not found'}), 400
    
    saved = {(log.exercise_id, log.set_number): log for log in SetLog.query.filter_by(session_id=session.id)}
    completions = {}
    for te, set_number, plan_a, plan_b in planned_sets(session.schedule):
        ex_type = te.exercise.exercise_type
        if ex_type == 'cardio':
            reps = request.form.get(f'actual_duration_{te.exercise_id}', type=int)
            weight = request.form.get(f'actual_distance_{te.exercise_id}', type=float)
        else:
            reps = request.form.get(f'reps_{te.exercise_id}_{set_number}', type=int)
            weight = request.form.get(f'weight_{te.exercise_id}_{set_number}', type=float)
        if reps is None:
            continue
        
        log = saved.pop((te.exercise_id, set_number), None)
        if log is None:
            log = SetLog(session_id=session.id, exercise_id=te.exercise_id, template_exercise_id=te.id,
                         set_number=set_number, planned_reps=plan_a, planned_weight=plan_b or 0)
            db.session.add(log)
        log.actual_reps = reps
        log.actual_weight = weight or 0
        log.calculate_completion(current_user.weight if ex_type == 'bodyweight' else None)
        completions[f'{te.exercise_id}_{set_number}'] = log.completion_percent
    
    # Оставшиеся в saved подходы не пришли в запросе — отметку с них сняли
    for log in saved.values():
        db.session.delete(log)
    
    db.session.commit()
    update_session_completion(session.id)
    return jsonify({'success': True, 'completions': completions})

@bp.route('/complete/<int:session_id>', methods=['POST'])
@limiter.exempt  # AJAX-автосохранение не должно упираться в общий лимит
@login_required
def complete_workout(session_id):
    """Завершение тренировки"""
        
    session = WorkoutSession.query.get_or_404(session_id)
    
    if session.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    if session.status == 'completed':
        return jsonify({'success': False, 'error': 'Training already completed'}), 400
    
    try:
        session.status = 'completed'
        session.is_completed = True  # если используете это поле
        db.session.commit()
        
        # Обновляем статус расписания
        if session.schedule:
            session.schedule.status = 'completed'
            db.session.commit()
        
        # Обновляем общий процент выполнения
        update_session_completion(session.id)
        
        return jsonify({'success': True, 'redirect': url_for('workouts.summary', session_id=session.id)})
    
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Ошибка завершения тренировки (session_id=%s)', session_id)
        return jsonify({'success': False, 'error': 'Не удалось завершить тренировку'}), 500

def planned_sets_by_exercise(schedule):
    """Сколько подходов запланировано по каждому упражнению: {exercise_id: число}.

    Учитываются только упражнения, которые есть и в плане, и в шаблоне, — ровно те,
    что показываются на экране тренировки. Кардио — один «подход».
    """
    if not schedule:
        return {}
    # Шаблон удалён — planned_data уже урезан до его упражнений на момент удаления (app/deletion.py)
    in_template = {te.exercise_id for te in schedule.template.template_exercises} if schedule.template else None
    planned = {}
    for exercise_id, plan in (schedule.planned_data or {}).items():
        if in_template is not None and int(exercise_id) not in in_template:
            continue
        if plan.get('input_type') == 'progressive':
            planned[int(exercise_id)] = len(plan.get('sets') or [])
        elif plan.get('input_type') == 'cardio':
            planned[int(exercise_id)] = 1
        else:
            planned[int(exercise_id)] = int(plan.get('sets') or 0)
    return planned


def session_totals(session):
    """Процент выполнения и тоннаж тренировки, без сохранения: (процент, тоннаж).

    По плану — сумма процентов отмеченных подходов делится на число запланированных
    (неотмеченный подход = 0%). Свободная тренировка — среднее по записанным подходам.
    """
    set_logs = SetLog.query.filter_by(session_id=session.id).all()
    if not set_logs:
        return 0, 0
    planned = sum(planned_sets_by_exercise(session.schedule).values())
    divider = max(planned, len(set_logs))
    percent = min(100, sum(log.completion_percent for log in set_logs) / divider)
    # Тоннаж — вес снаряда × повторения, только силовые: у кардио в этих полях минуты и км,
    # собственный вес в тоннаж не входит (решение владельца проекта)
    tonnage = sum((log.actual_reps or 0) * (log.actual_weight or 0)
                  for log in set_logs if log.exercise and log.exercise.exercise_type == 'strength')
    return round(percent, 1), tonnage


def update_session_completion(session_id):
    """Пересчитывает и сохраняет процент выполнения и тоннаж тренировки"""
    session = db.session.get(WorkoutSession, session_id)
    if not session:
        return
    session.completion_percent, session.total_tonnage = session_totals(session)
    db.session.commit()

@bp.route('/summary/<int:session_id>')
@login_required
def summary(session_id):
    """Результаты завершённой тренировки"""
    session = WorkoutSession.query.get_or_404(session_id)
    
    if session.user_id != current_user.id:
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('workouts.index'))
    
    set_logs = SetLog.query.filter_by(session_id=session.id).order_by(SetLog.id).all()
    
    # Группируем по упражнениям
    exercises_summary = {}
    for log in set_logs:
        if log.exercise_id not in exercises_summary:
            exercises_summary[log.exercise_id] = {
                'name': log.exercise.name,
                'exercise_type': log.exercise.exercise_type,
                'sets': [],
                'total_completion': 0
            }
        exercises_summary[log.exercise_id]['sets'].append(log)
    
    # Процент по упражнению — от запланированных подходов (как и общий процент тренировки)
    planned = planned_sets_by_exercise(session.schedule)
    for ex_id, data in exercises_summary.items():
        sets = data['sets']
        divider = max(planned.get(ex_id, 0), len(sets))
        data['total_completion'] = min(100, sum(s.completion_percent for s in sets) / divider) if divider else 0
        data['planned_sets'] = planned.get(ex_id)
    
    return render_template('workouts/summary.html', 
                         session=session,
                         exercises_summary=exercises_summary,
                         sets_count=len(set_logs),
                         title=session_title(session),
                         date_text=human_date(local_date(session.date)))

@bp.route('/skip/<int:schedule_id>', methods=['POST'])
@login_required
def skip_workout(schedule_id):
    """Пропустить тренировку"""
    schedule = WorkoutSchedule.query.get_or_404(schedule_id)
    
    if schedule.user_id != current_user.id:
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('workouts.index'))
    
    schedule.status = 'skipped'
    db.session.commit()
    
    flash('Тренировка отмечена как пропущенная', 'info')
    return redirect(url_for('workouts.index'))

@bp.route('/move_to_today/<int:schedule_id>', methods=['POST'])
@login_required
def move_to_today(schedule_id):
    """Перенести пропущенную тренировку на сегодня"""
    schedule = WorkoutSchedule.query.get_or_404(schedule_id)
    if schedule.user_id != current_user.id or schedule.status != 'planned':
        flash('Эту тренировку нельзя перенести', 'danger')
        return redirect(url_for('workouts.index'))
    schedule.scheduled_date = local_today()
    db.session.commit()
    flash(f'«{schedule.template.name}» перенесена на сегодня', 'success')
    return redirect(url_for('workouts.index'))

@bp.route('/postpone/<int:schedule_id>', methods=['POST'])
@login_required
def postpone_workout(schedule_id):
    """Перенести тренировку на завтра"""
    schedule = WorkoutSchedule.query.get_or_404(schedule_id)
    
    if schedule.user_id != current_user.id:
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('workouts.index'))
    
    from datetime import timedelta
    schedule.scheduled_date = schedule.scheduled_date + timedelta(days=1)
    db.session.commit()
    
    flash('Тренировка перенесена на завтра', 'info')
    return redirect(url_for('workouts.index'))

def get_active_free_session(session_id=None):
    """Незавершённая свободная тренировка текущего пользователя (без расписания).
    
    Если передан session_id — возвращает эту сессию, при условии что она свободная,
    незавершённая и принадлежит пользователю; иначе — последнюю такую сессию или None.
    """
    query = WorkoutSession.query.filter_by(
        user_id=current_user.id,
        is_completed=False,
        schedule_id=None
    )
    if session_id and str(session_id).isdigit():
        workout_session = query.filter_by(id=int(session_id)).first()
        if workout_session:
            return workout_session
    return query.order_by(WorkoutSession.date.desc()).first()

@bp.route('/free_workout', methods=['GET', 'POST'])
@login_required
def free_workout():
    """Свободная тренировка (без шаблона, ручной ввод упражнений)"""
    
    # Только свободные сессии: у тренировки по расписанию свои подходы, их трогать нельзя
    workout_session = get_active_free_session(request.args.get('session_id'))
    
    if request.method == 'POST':
        if not workout_session:
            workout_session = WorkoutSession(
                user_id=current_user.id,
                schedule_id=None,
                template_id=None,
                date=datetime.utcnow(),
                status='in_progress',
                is_completed=False
            )
            db.session.add(workout_session)
            db.session.commit()
        
        if workout_session.is_completed:
            flash('Эта тренировка уже завершена', 'warning')
            return redirect(url_for('workouts.summary', session_id=workout_session.id))
        
        # Получаем данные из формы
        exercise_ids = request.form.getlist('exercise_id[]')
        set_numbers = request.form.getlist('set_number[]')
        weights = request.form.getlist('weight[]')
        reps_list = request.form.getlist('reps[]')
        is_completed = request.form.get('action') == 'complete'
        
        # Форма присылает все отмеченные подходы — прежние перезаписываем
        SetLog.query.filter_by(session_id=workout_session.id).delete()
        
        saved_count = 0
        for i in range(len(exercise_ids)):
            if not exercise_ids[i] or exercise_ids[i] == 'None':
                continue
            
            exercise_id = int(exercise_ids[i])
            exercise_obj = db.session.get(Exercise, exercise_id)
            if not exercise_obj:
                continue
            
            set_number = int(set_numbers[i]) if i < len(set_numbers) and set_numbers[i] else 1
            weight = float(weights[i]) if i < len(weights) and weights[i] else 0
            reps = int(reps_list[i]) if i < len(reps_list) and reps_list[i] else 0
            if reps == 0:
                continue
            
            set_log = SetLog(
                session_id=workout_session.id,
                exercise_id=exercise_id,
                set_number=set_number,
                planned_reps=reps,
                planned_weight=weight,
                actual_reps=reps,
                actual_weight=weight
            )
            set_log.calculate_completion(current_user.weight if exercise_obj.exercise_type == 'bodyweight' else None)
            db.session.add(set_log)
            saved_count += 1
        
        db.session.commit()
        update_session_completion(workout_session.id)
        
        if is_completed:
            workout_session.is_completed = True
            workout_session.status = 'completed'
            db.session.commit()
        
        # Фоновое сохранение со страницы (fetch) — отвечаем JSON
        if request.headers.get('X-Requested-With') == 'fetch':
            return jsonify({
                'success': True,
                'session_id': workout_session.id,
                'saved': saved_count,
                'redirect': url_for('workouts.summary', session_id=workout_session.id) if is_completed else None,
            })
        
        if is_completed:
            flash('Свободная тренировка завершена!', 'success')
            return redirect(url_for('workouts.summary', session_id=workout_session.id))
        flash(f'Прогресс сохранён! ({saved_count} подходов)', 'success')
        return redirect(url_for('workouts.free_workout', session_id=workout_session.id))
    
    # GET — сохранённые подходы, сгруппированные по упражнениям в порядке добавления
    groups = []
    if workout_session:
        by_exercise = {}
        for log in SetLog.query.filter_by(session_id=workout_session.id).order_by(SetLog.id).all():
            if log.exercise_id not in by_exercise:
                by_exercise[log.exercise_id] = {
                    'id': log.exercise_id,
                    'name': log.exercise.name,
                    'type': log.exercise.exercise_type,
                    'sets': [],
                }
                groups.append(by_exercise[log.exercise_id])
            by_exercise[log.exercise_id]['sets'].append({'w': log.actual_weight or 0, 'r': log.actual_reps})
    
    # «Прошлый раз» — первый подход последней завершённой тренировки с этим упражнением
    for group in groups:
        last_log = SetLog.query.join(WorkoutSession).filter(
            WorkoutSession.user_id == current_user.id,
            WorkoutSession.is_completed.is_(True),
            SetLog.exercise_id == group['id'],
            SetLog.actual_reps.isnot(None)
        ).order_by(WorkoutSession.date.desc(), SetLog.set_number).first()
        group['prev'] = {'w': last_log.actual_weight or 0, 'r': last_log.actual_reps} if last_log else None
    
    catalog = [{
        'id': e.id,
        'name': e.name,
        'type': e.exercise_type,
        'group': e.muscle_group.display_name if e.muscle_group else '',
    } for e in Exercise.query.order_by(Exercise.name).all()]
    
    return render_template('workouts/free_workout.html',
                           groups=groups,
                           catalog=catalog,
                           workout_session=workout_session)

@bp.route('/delete_schedule/<int:schedule_id>', methods=['POST'])
@login_required
def delete_schedule(schedule_id):
    """Удаление запланированной программы (только если нет выполненных тренировок)"""
    schedule = WorkoutSchedule.query.get_or_404(schedule_id)
    
    # Проверка прав
    if schedule.user_id != current_user.id:
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('workouts.index'))
    
    # Сохраняем имя шаблона ДО удаления
    template_name = schedule.template.name if schedule.template else "Программа"
    
    # Проверка: есть ли завершённые тренировки по этому расписанию
    if schedule.session and schedule.session.is_completed:
        flash(f'Нельзя удалить программу "{template_name}", по которой уже есть выполненные тренировки', 'danger')
        return redirect(url_for('workouts.index'))
    
    # Если тренировка была начата, но не завершена, удаляем и сессию
    if schedule.session and not schedule.session.is_completed:
        db.session.delete(schedule.session)
    
    db.session.delete(schedule)
    db.session.commit()
    
    flash(f'Программа "{template_name}" удалена из расписания', 'success')
    return redirect(url_for('workouts.index'))