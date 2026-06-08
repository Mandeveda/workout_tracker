from flask import render_template, redirect, url_for, flash, request, Blueprint, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from app import db
from app.models import WorkoutSchedule, WorkoutSession, SetLog, Exercise, TemplateExercise
import json

bp = Blueprint('workouts', __name__, url_prefix='/workouts')

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
        flash('Ошибка: расписание не найдено', 'danger')
        return redirect(url_for('workouts.index'))
    
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
                            'actual_weight': saved_log.actual_weight if saved_log and saved_log.actual_weight else ''
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
                            'actual_weight': saved_log.actual_weight if saved_log and saved_log.actual_weight else ''
                        })
                
                exercises_data.append({
                    'template_exercise_id': te.id,
                    'exercise_id': te.exercise_id,
                    'exercise_name': te.exercise.name,
                    'exercise_type': exercise_type,
                    'sets': sets_data
                })
    
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
    
    db.session.commit()
    
    # Обновляем общий процент выполнения
    update_session_completion(session.id)
    
    return jsonify({'success': True, 'completions': completions})

@bp.route('/complete/<int:session_id>', methods=['POST'])
@login_required
def complete_workout(session_id):
    """Завершение тренировки"""
    from flask_wtf.csrf import generate_csrf
    
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
    
    if set_logs:
        total_percent = sum(log.completion_percent for log in set_logs) / len(set_logs)
        total_tonnage = sum((log.actual_reps or 0) * (log.actual_weight or 0) for log in set_logs)
        
        session = WorkoutSession.query.get(session_id)
        if session:
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

@bp.route('/skip/<int:schedule_id>')
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

@bp.route('/postpone/<int:schedule_id>')
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

@bp.route('/free_workout', methods=['GET', 'POST'])
@login_required
def free_workout():
    """Свободная тренировка (без шаблона, ручной ввод упражнений)"""
    
    if request.method == 'POST':
        # Проверяем, была ли нажата кнопка завершения
        is_completed = request.form.get('complete') == '1'
        
        # Получаем ID сессии из скрытого поля формы
        session_id = request.form.get('session_id')
        
        # Проверяем, есть ли уже активная сессия
        if session_id and session_id.isdigit():
            workout_session = WorkoutSession.query.get(int(session_id))
            if workout_session and workout_session.user_id == current_user.id and not workout_session.is_completed:
                pass
            else:
                workout_session = None
        else:
            workout_session = None
        
        # Если нет активной сессии, создаём новую
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
        
        # Если тренировка уже завершена, не даём её изменять
        if workout_session.is_completed:
            flash('Эта тренировка уже завершена', 'warning')
            return redirect(url_for('workouts.summary', session_id=workout_session.id))
        
        # Получаем данные из формы
        exercise_ids = request.form.getlist('exercise_id')
        log_ids = request.form.getlist('log_id')  # ID существующих логов
        set_numbers = request.form.getlist('set_number')
        weights = request.form.getlist('weight')
        reps_list = request.form.getlist('reps')
        progressive_data_list = request.form.getlist('progressive_data')
        input_types = request.form.getlist('input_type')

        # Собираем ID логов, которые нужно сохранить
        kept_log_ids = []
        
        # Обрабатываем каждое упражнение
        saved_count = 0
        for i in range(len(exercise_ids)):
            if not exercise_ids[i] or exercise_ids[i] == 'None':
                continue
                
            exercise_id = int(exercise_ids[i])
            exercise_obj = Exercise.query.get(exercise_id)
            
            if not exercise_obj:
                continue
            
            input_type = input_types[i] if i < len(input_types) else 'fixed'
    
            if input_type == 'progressive':
                # Обработка progressive режима
                if i < len(progressive_data_list) and progressive_data_list[i]:
                    try:
                        progressive_sets = json.loads(progressive_data_list[i])
                        for set_info in progressive_sets:
                            # Создаём лог для каждого подхода
                            set_log = SetLog(
                                session_id=workout_session.id,
                                exercise_id=exercise_id,
                                set_number=set_info.get('set_number', 1),
                                planned_reps=set_info.get('reps', 0),
                                planned_weight=set_info.get('weight', 0),
                                actual_reps=set_info.get('reps', 0),
                                actual_weight=set_info.get('weight', 0)
                            )
                            
                            if exercise_obj.exercise_type == 'bodyweight':
                                set_log.calculate_completion(current_user.weight)
                            else:
                                set_log.calculate_completion()
                            
                            db.session.add(set_log)
                            db.session.flush()  # Чтобы получить ID
                            kept_log_ids.append(set_log.id)  # ВАЖНО: добавляем ID в список
                            saved_count += 1
                    except json.JSONDecodeError:
                        flash(f'Ошибка в данных упражнения {exercise_obj.name}', 'danger')
                        continue
            else:    
                weight = float(weights[i]) if i < len(weights) and weights[i] and weights[i] != 'None' else 0
                reps = int(reps_list[i]) if i < len(reps_list) and reps_list[i] and reps_list[i] != 'None' else 0
                
                if reps == 0:
                    continue  # Пропускаем упражнения без повторений
                    
                set_number = int(set_numbers[i]) if i < len(set_numbers) and set_numbers[i] and set_numbers[i] != 'None' else 1
                
                log_id = log_ids[i] if i < len(log_ids) and log_ids[i] and log_ids[i].isdigit() else None
                
                if log_id:
                    # Обновляем существующий лог
                    existing_log = SetLog.query.get(int(log_id))
                    if existing_log and existing_log.session_id == workout_session.id:
                        existing_log.set_number = set_number
                        existing_log.planned_reps = reps
                        existing_log.planned_weight = weight
                        existing_log.actual_reps = reps
                        existing_log.actual_weight = weight
                        
                        if exercise_obj.exercise_type == 'bodyweight':
                            existing_log.calculate_completion(current_user.weight)
                        else:
                            existing_log.calculate_completion()
                        
                        kept_log_ids.append(int(log_id))
                        saved_count += 1
                else:
                    # Создаём новый лог
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
                    db.session.flush()  # Чтобы получить ID
                    kept_log_ids.append(set_log.id)
                    saved_count += 1
        
        # Удаляем логи, которые не были сохранены (удалённые упражнения)
        all_session_logs = SetLog.query.filter_by(session_id=workout_session.id).all()
        for log in all_session_logs:
            if log.id not in kept_log_ids:
                db.session.delete(log)
        
        db.session.commit()
        
        # Обновляем проценты и тоннаж
        if saved_count > 0:
            update_session_completion(workout_session.id)
        
        if is_completed:
            workout_session.is_completed = True
            workout_session.status = 'completed'
            db.session.commit()
            flash('Свободная тренировка завершена и сохранена!', 'success')
            return redirect(url_for('workouts.summary', session_id=workout_session.id))
        else:
            flash(f'Прогресс сохранён! ({saved_count} упражнений)', 'success')
            return redirect(url_for('workouts.free_workout', session_id=workout_session.id))
    
    # GET запрос — показываем форму
    session_id = request.args.get('session_id')
    saved_logs = []
    workout_session = None
    
    if session_id and session_id.isdigit():
        try:
            workout_session = WorkoutSession.query.get(int(session_id))
            if workout_session and workout_session.user_id == current_user.id and not workout_session.is_completed:
                saved_logs = SetLog.query.filter_by(session_id=workout_session.id).order_by(SetLog.id).all()
            else:
                session_id = None
        except (ValueError, TypeError):
            session_id = None
    
    exercises = Exercise.query.order_by(Exercise.name).all()
    
    # ВАЖНО: возвращаем шаблон для GET запроса
    return render_template('workouts/free_workout.html', 
                         exercises=exercises, 
                         saved_logs=saved_logs,
                         session_id=session_id)
