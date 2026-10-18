from flask import render_template, redirect, url_for, flash, request, Blueprint, jsonify
from flask_login import login_required, current_user
from flask_wtf.csrf import generate_csrf
from datetime import datetime
from app import db, limiter
from app.models import WorkoutSchedule, WorkoutSession, SetLog, Exercise, TemplateExercise
import json
import logging

bp = Blueprint('workouts', __name__, url_prefix='/workouts')

# Настройка логирования
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@bp.route('/')
@login_required
def index():
    """Список тренировок на сегодня и предстоящие"""
    today = datetime.utcnow().date()
    
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
                         upcoming=upcoming,
                         history=history)

@bp.route('/start')
@bp.route('/start/<int:schedule_id>')
@login_required
def start_workout(schedule_id=None):
    """Начать тренировку"""
    today = datetime.utcnow().date()
    
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
        date=datetime.utcnow(),
        status='in_progress',  # Новый статус
        is_completed=False      # Новое поле
    )
    db.session.add(session)
    db.session.commit()
    
    flash('Тренировка начата! Заполните результаты подходов.', 'success')
    return redirect(url_for('workouts.perform', session_id=session.id))

@bp.route('/perform/<int:session_id>', methods=['GET', 'POST'])
@login_required
def perform(session_id):
    """Выполнение тренировки (ввод результатов с возможностью редактирования)"""
    session = WorkoutSession.query.get_or_404(session_id)
    
    if session.user_id != current_user.id:
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('workouts.index'))
    
    # Если тренировка завершена, перенаправляем на summary
    if session.is_completed:
        flash('Эта тренировка уже завершена', 'info')
        return redirect(url_for('workouts.summary', session_id=session.id))
    
    schedule = session.schedule
    if not schedule:
        # Сессия без расписания — это свободная тренировка
        return redirect(url_for('workouts.free_workout', session_id=session.id))
    
    planned_data = schedule.planned_data
    
    # Получаем упражнения из шаблона
    template_exercises = TemplateExercise.query.filter_by(
        template_id=schedule.template.id
    ).order_by(TemplateExercise.order).all()
    
    # Получаем существующие логи для этой сессии
    existing_logs = {log.id: log for log in SetLog.query.filter_by(session_id=session.id).all()}
    
    # Группируем логи по упражнениям и подходам для быстрого доступа
    log_by_exercise_set = {}
    for log in existing_logs.values():
        log_by_exercise_set[(log.exercise_id, log.set_number)] = log
    
    # Собираем информацию об упражнениях с заполненными данными
    exercises_data = []
    for te in template_exercises:
        exercise_id = str(te.exercise_id)
        exercise_type = te.exercise.exercise_type
        
        if exercise_id in planned_data:
            exercise_plan = planned_data[exercise_id]
            
            if exercise_type == 'cardio':
                # Проверяем, есть ли сохранённые данные для кардио
                cardio_log = log_by_exercise_set.get((te.exercise_id, 1))
                
                exercises_data.append({
                    'template_exercise_id': te.id,
                    'exercise_id': te.exercise_id,
                    'exercise_name': te.exercise.name,
                    'exercise_type': 'cardio',
                    'planned_duration': exercise_plan.get('duration', 30),
                    'planned_distance': exercise_plan.get('distance', 0),
                    'planned_heart_rate': exercise_plan.get('target_heart_rate'),
                    'actual_duration': cardio_log.actual_reps if cardio_log and cardio_log.actual_reps else '',
                    'actual_distance': cardio_log.actual_weight if cardio_log and cardio_log.actual_weight else '',
                    'actual_heart_rate': None  # Можно добавить отдельное поле в SetLog
                })
            else:
                # strength или bodyweight
                sets_data = []
                if exercise_plan['input_type'] == 'fixed':
                    for i in range(1, exercise_plan['sets'] + 1):
                        # Проверяем, есть ли сохранённые данные для этого подхода
                        saved_log = log_by_exercise_set.get((te.exercise_id, i))
                        
                        sets_data.append({
                            'set_number': i,
                            'planned_reps': exercise_plan['reps'],
                            'planned_weight': exercise_plan.get('weight', 0),
                            'actual_reps': saved_log.actual_reps if saved_log and saved_log.actual_reps else '',
                            'actual_weight': saved_log.actual_weight if saved_log and saved_log.actual_weight is not None else ''
                        })
                else:
                    for set_info in exercise_plan['sets']:
                        set_num = set_info['set_number']
                        saved_log = log_by_exercise_set.get((te.exercise_id, set_num))
                        
                        sets_data.append({
                            'set_number': set_num,
                            'planned_reps': set_info['reps'],
                            'planned_weight': set_info.get('weight', 0),
                            'actual_reps': saved_log.actual_reps if saved_log and saved_log.actual_reps else '',
                            'actual_weight': saved_log.actual_weight if saved_log and saved_log.actual_weight is not None else ''
                        })
                
                exercises_data.append({
                    'template_exercise_id': te.id,
                    'exercise_id': te.exercise_id,
                    'exercise_name': te.exercise.name,
                    'exercise_type': exercise_type,
                    'sets': sets_data
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
    
    if request.method == 'POST':
        # Обработка сохранения (обычная отправка формы для завершения)
        # Сохраняем результаты (обновляем существующие или создаём новые)
        for exercise in exercises_data:
            if exercise['exercise_type'] == 'cardio':
                actual_duration = request.form.get(f'actual_duration_{exercise["exercise_id"]}', type=int)
                actual_distance = request.form.get(f'actual_distance_{exercise["exercise_id"]}', type=float)
                
                # Ищем существующий лог
                existing_log = SetLog.query.filter_by(
                    session_id=session.id,
                    exercise_id=exercise['exercise_id'],
                    set_number=1
                ).first()
                
                if actual_duration or actual_distance:
                    if existing_log:
                        # Обновляем существующий
                        existing_log.actual_reps = actual_duration
                        existing_log.actual_weight = actual_distance
                        existing_log.calculate_completion(
                            current_user.weight if exercise['exercise_type'] == 'bodyweight' else None
                        )
                    else:
                        # Создаём новый
                        set_log = SetLog(
                            session_id=session.id,
                            exercise_id=exercise['exercise_id'],
                            template_exercise_id=exercise['template_exercise_id'],
                            set_number=1,
                            planned_reps=exercise.get('planned_duration', 0),
                            planned_weight=exercise.get('planned_distance', 0),
                            actual_reps=actual_duration,
                            actual_weight=actual_distance
                        )
                        set_log.calculate_completion()
                        db.session.add(set_log)
                
            else:
                # Силовые и bodyweight
                for set_info in exercise['sets']:
                    set_number = set_info['set_number']
                    actual_reps = request.form.get(f'reps_{exercise["exercise_id"]}_{set_number}', type=int)
                    actual_weight = request.form.get(f'weight_{exercise["exercise_id"]}_{set_number}', type=float)
                    
                    if actual_reps is not None:
                        # Ищем существующий лог
                        existing_log = SetLog.query.filter_by(
                            session_id=session.id,
                            exercise_id=exercise['exercise_id'],
                            set_number=set_number
                        ).first()
                        
                        if existing_log:
                            # Обновляем существующий
                            existing_log.actual_reps = actual_reps
                            existing_log.actual_weight = actual_weight if actual_weight else 0
                            if exercise['exercise_type'] == 'bodyweight':
                                existing_log.calculate_completion(current_user.weight)
                            else:
                                existing_log.calculate_completion()
                        else:
                            # Создаём новый
                            set_log = SetLog(
                                session_id=session.id,
                                exercise_id=exercise['exercise_id'],
                                template_exercise_id=exercise['template_exercise_id'],
                                set_number=set_number,
                                planned_reps=set_info['planned_reps'],
                                planned_weight=set_info.get('planned_weight', 0),
                                actual_reps=actual_reps,
                                actual_weight=actual_weight if actual_weight else 0
                            )
                            if exercise['exercise_type'] == 'bodyweight':
                                set_log.calculate_completion(current_user.weight)
                            else:
                                set_log.calculate_completion()
                            db.session.add(set_log)
        
        db.session.commit()
        
        # Обновляем процент выполнения тренировки
        update_session_completion(session.id)
        
        # Проверяем, нажата ли кнопка завершения
        if request.form.get('complete'):
            session.is_completed = True
            session.status = 'completed'
            db.session.commit()
            
            # Обновляем статус расписания
            if session.schedule:
                session.schedule.status = 'completed'
                db.session.commit()
            
            flash('Тренировка успешно завершена!', 'success')
            return redirect(url_for('workouts.summary', session_id=session.id))
        else:
            flash('Прогресс сохранён!', 'success')
            # Остаёмся на той же странице для продолжения редактирования
            return redirect(url_for('workouts.perform', session_id=session.id))
    
    return render_template('workouts/perform.html', 
                         session=session,
                         exercises_data=exercises_data)

@bp.route('/save_progress/<int:session_id>', methods=['POST'])
@limiter.exempt  # AJAX-автосохранение не должно упираться в общий лимит
@login_required
def save_progress(session_id):
    """Сохранение текущего прогресса тренировки (AJAX)"""
    session = WorkoutSession.query.get_or_404(session_id)
    
    if session.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    if session.is_completed:
        return jsonify({'success': False, 'error': 'Training already completed'}), 400
    
    schedule = session.schedule
    if not schedule:
        return jsonify({'success': False, 'error': 'Schedule not found'}), 400
    
    planned_data = schedule.planned_data
    
    template_exercises = TemplateExercise.query.filter_by(
        template_id=schedule.template.id
    ).order_by(TemplateExercise.order).all()
    
    completions = {}
    
    for te in template_exercises:
        exercise_id = str(te.exercise_id)
        exercise_type = te.exercise.exercise_type
        
        if exercise_id in planned_data:
            exercise_plan = planned_data[exercise_id]
            
            if exercise_type == 'cardio':
                actual_duration = request.form.get(f'actual_duration_{te.exercise_id}', type=int)
                actual_distance = request.form.get(f'actual_distance_{te.exercise_id}', type=float)
                
                existing_log = SetLog.query.filter_by(
                    session_id=session.id,
                    exercise_id=te.exercise_id,
                    set_number=1
                ).first()
                
                if actual_duration is not None:
                    if existing_log:
                        existing_log.actual_reps = actual_duration
                        existing_log.actual_weight = actual_distance if actual_distance else 0
                        existing_log.calculate_completion()
                    else:
                        set_log = SetLog(
                            session_id=session.id,
                            exercise_id=te.exercise_id,
                            template_exercise_id=te.id,
                            set_number=1,
                            planned_reps=exercise_plan.get('duration', 30),
                            planned_weight=exercise_plan.get('distance', 0),
                            actual_reps=actual_duration,
                            actual_weight=actual_distance if actual_distance else 0
                        )
                        set_log.calculate_completion()
                        db.session.add(set_log)
                    
                    completions[f'{te.exercise_id}_1'] = existing_log.completion_percent if existing_log else set_log.completion_percent
                    
            else:
                # Strength или bodyweight
                if exercise_plan['input_type'] == 'fixed':
                    for i in range(1, exercise_plan['sets'] + 1):
                        actual_reps = request.form.get(f'reps_{te.exercise_id}_{i}', type=int)
                        actual_weight = request.form.get(f'weight_{te.exercise_id}_{i}', type=float)
                        
                        if actual_reps is not None:
                            existing_log = SetLog.query.filter_by(
                                session_id=session.id,
                                exercise_id=te.exercise_id,
                                set_number=i
                            ).first()
                            
                            if existing_log:
                                existing_log.actual_reps = actual_reps
                                existing_log.actual_weight = actual_weight if actual_weight else 0
                                if exercise_type == 'bodyweight':
                                    existing_log.calculate_completion(current_user.weight)
                                else:
                                    existing_log.calculate_completion()
                                completions[f'{te.exercise_id}_{i}'] = existing_log.completion_percent
                            else:
                                set_log = SetLog(
                                    session_id=session.id,
                                    exercise_id=te.exercise_id,
                                    template_exercise_id=te.id,
                                    set_number=i,
                                    planned_reps=exercise_plan['reps'],
                                    planned_weight=exercise_plan.get('weight', 0),
                                    actual_reps=actual_reps,
                                    actual_weight=actual_weight if actual_weight else 0
                                )
                                if exercise_type == 'bodyweight':
                                    set_log.calculate_completion(current_user.weight)
                                else:
                                    set_log.calculate_completion()
                                db.session.add(set_log)
                                completions[f'{te.exercise_id}_{i}'] = set_log.completion_percent
                else:
                    # Progressive
                    for set_info in exercise_plan['sets']:
                        set_num = set_info['set_number']
                        actual_reps = request.form.get(f'reps_{te.exercise_id}_{set_num}', type=int)
                        actual_weight = request.form.get(f'weight_{te.exercise_id}_{set_num}', type=float)
                        
                        if actual_reps is not None:
                            existing_log = SetLog.query.filter_by(
                                session_id=session.id,
                                exercise_id=te.exercise_id,
                                set_number=set_num
                            ).first()
                            
                            if existing_log:
                                existing_log.actual_reps = actual_reps
                                existing_log.actual_weight = actual_weight if actual_weight else 0
                                if exercise_type == 'bodyweight':
                                    existing_log.calculate_completion(current_user.weight)
                                else:
                                    existing_log.calculate_completion()
                                completions[f'{te.exercise_id}_{set_num}'] = existing_log.completion_percent
                            else:
                                set_log = SetLog(
                                    session_id=session.id,
                                    exercise_id=te.exercise_id,
                                    template_exercise_id=te.id,
                                    set_number=set_num,
                                    planned_reps=set_info['reps'],
                                    planned_weight=set_info.get('weight', 0),
                                    actual_reps=actual_reps,
                                    actual_weight=actual_weight if actual_weight else 0
                                )
                                if exercise_type == 'bodyweight':
                                    set_log.calculate_completion(current_user.weight)
                                else:
                                    set_log.calculate_completion()
                                db.session.add(set_log)
                                completions[f'{te.exercise_id}_{set_num}'] = set_log.completion_percent
    
    # Подходы, которых нет в запросе, считаются не выполненными (отметку сняли) — удаляем
    for log in SetLog.query.filter_by(session_id=session.id).all():
        if f'{log.exercise_id}_{log.set_number}' not in completions:
            db.session.delete(log)
    
    db.session.commit()
    
    # Обновляем общий процент выполнения
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
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

def update_session_completion(session_id):
    """Обновляет общий процент выполнения тренировки"""
    set_logs = SetLog.query.filter_by(session_id=session_id).all()
    session = WorkoutSession.query.get(session_id)
    if not session:
        return
    
    if set_logs:
        total_percent = sum(log.completion_percent for log in set_logs) / len(set_logs)
        total_tonnage = sum((log.actual_reps or 0) * (log.actual_weight or 0) for log in set_logs)
    else:
        total_percent, total_tonnage = 0, 0
    
    session.completion_percent = round(total_percent, 1)
    session.total_tonnage = total_tonnage
    db.session.commit()

@bp.route('/summary/<int:session_id>')
@login_required
def summary(session_id):
    """Результаты завершённой тренировки"""
    session = WorkoutSession.query.get_or_404(session_id)
    
    if session.user_id != current_user.id:
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('workouts.index'))
    
    set_logs = SetLog.query.filter_by(session_id=session.id).all()
    
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
    
    # Считаем средний процент по упражнениям
    for ex_id in exercises_summary:
        sets = exercises_summary[ex_id]['sets']
        if sets:
            exercises_summary[ex_id]['total_completion'] = sum(s.completion_percent for s in sets) / len(sets)
        else:
            exercises_summary[ex_id]['total_completion'] = 0
    
    return render_template('workouts/summary.html', 
                         session=session,
                         exercises_summary=exercises_summary)

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
        
        logger.debug("=" * 60)
        logger.debug("📥 ПОЛУЧЕНЫ ДАННЫЕ ИЗ ФОРМЫ:")
        
        # Получаем данные из формы
        exercise_ids = request.form.getlist('exercise_id[]')
        set_numbers = request.form.getlist('set_number[]')
        weights = request.form.getlist('weight[]')
        reps_list = request.form.getlist('reps[]')
        is_completed = request.form.get('action') == 'complete'
        
        # Удаляем старые логи
        logger.debug(f"  exercise_id[]: {exercise_ids}")
        logger.debug(f"  set_number[]: {set_numbers}")
        logger.debug(f"  weight[]: {weights}")
        logger.debug(f"  reps[]: {reps_list}")
        logger.debug(f"  is_completed: {request.form.get('complete')}")
        
        # Группируем по индексам для наглядности
        logger.debug("📋 ДАННЫЕ ПО УПРАЖНЕНИЯМ:")
        for i in range(len(exercise_ids)):
            if exercise_ids[i] and exercise_ids[i] != 'None':
                logger.debug(f"  [{i}] Упражнение {exercise_ids[i]}: "
                           f"подход {set_numbers[i]}, "
                           f"вес {weights[i]}, "
                           f"повторы {reps_list[i]}")
        
        # Удаляем старые логи
        SetLog.query.filter_by(session_id=workout_session.id).delete()
        
        saved_count = 0
        created_logs = []
        
        for i in range(len(exercise_ids)):
            if not exercise_ids[i] or exercise_ids[i] == 'None':
                continue
            
            exercise_id = int(exercise_ids[i])
            exercise_obj = Exercise.query.get(exercise_id)
            
            if not exercise_obj:
                logger.warning(f"⚠️ Упражнение {exercise_id} не найдено в БД")
                continue
            
            set_number = int(set_numbers[i]) if i < len(set_numbers) and set_numbers[i] else 1
            weight = float(weights[i]) if i < len(weights) and weights[i] else 0
            reps = int(reps_list[i]) if i < len(reps_list) and reps_list[i] else 0
            
            if reps == 0:
                logger.debug(f"  ⏭️ Пропускаем упражнение {exercise_id}: повторений 0")
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
            
            if exercise_obj.exercise_type == 'bodyweight':
                set_log.calculate_completion(current_user.weight)
            else:
                set_log.calculate_completion()
            
            db.session.add(set_log)
            created_logs.append({
                'exercise_id': exercise_id,
                'set_number': set_number,
                'weight': weight,
                'reps': reps,
                'completion': set_log.completion_percent
            })
            saved_count += 1
        
        # ЛОГИРУЕМ ЧТО БЫЛО СОЗДАНО
        logger.debug("=" * 60)
        logger.debug("💾 СОЗДАНЫ ЛОГИ:")
        for log in created_logs:
            logger.debug(f"  Упр.{log['exercise_id']} подход {log['set_number']}: "
                        f"{log['weight']} кг × {log['reps']} повт., "
                        f"выполнение {log['completion']:.1f}%")
        
        db.session.commit()
        logger.debug(f"✅ Сохранено {saved_count} подходов в БД")
        
        # ПРОВЕРЯЕМ ЧТО СОХРАНИЛОСЬ В БАЗЕ
        saved_check = SetLog.query.filter_by(session_id=workout_session.id).all()
        logger.debug("=" * 60)
        logger.debug("📂 ЧТО СОХРАНИЛОСЬ В БАЗЕ:")
        for log in saved_check:
            exercise = Exercise.query.get(log.exercise_id)
            logger.debug(f"  Упр.{log.exercise_id} ({exercise.name if exercise else '?'}) "
                        f"подход {log.set_number}: "
                        f"{log.actual_weight} кг × {log.actual_reps} повт.")
        
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