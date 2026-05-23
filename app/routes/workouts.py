from flask import render_template, redirect, url_for, flash, request, Blueprint
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
        user_id=current_user.id
    ).order_by(WorkoutSession.date.desc()).limit(10).all()
    
    return render_template('workouts/index.html', 
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
    
    existing_session = WorkoutSession.query.filter_by(schedule_id=schedule.id).first()
    
    if existing_session:
        flash('Тренировка уже была начата. Продолжите выполнение.', 'info')
        return redirect(url_for('workouts.perform', session_id=existing_session.id))
    
    # ИСПРАВЛЕНИЕ: добавляем template_id из расписания
    session = WorkoutSession(
        user_id=current_user.id,
        schedule_id=schedule.id,
        template_id=schedule.template_id,  # <-- ДОБАВИТЬ ЭТУ СТРОКУ
        date=datetime.utcnow(),
        status='completed'
    )
    db.session.add(session)
    db.session.commit()
    
    flash('Тренировка начата! Заполните результаты подходов.', 'success')
    return redirect(url_for('workouts.perform', session_id=session.id))

@bp.route('/perform/<int:session_id>', methods=['GET', 'POST'])
@login_required
def perform(session_id):
    """Выполнение тренировки (ввод результатов)"""
    session = WorkoutSession.query.get_or_404(session_id)
    
    if session.user_id != current_user.id:
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('workouts.index'))
    
    # Проверяем, что тренировка ещё не завершена (нет логов)
    existing_logs = SetLog.query.filter_by(session_id=session.id).first()
    if existing_logs:
        flash('Эта тренировка уже была завершена', 'warning')
        return redirect(url_for('workouts.summary', session_id=session.id))
    
    schedule = session.schedule
    planned_data = schedule.planned_data
    
    # Получаем упражнения из шаблона
    template_exercises = TemplateExercise.query.filter_by(template_id=schedule.template.id).order_by(TemplateExercise.order).all()
    
    # Собираем информацию об упражнениях
    exercises_data = []
    for te in template_exercises:
        exercise_id = str(te.exercise_id)
        exercise_type = te.exercise.exercise_type
        
        if exercise_id in planned_data:
            exercise_plan = planned_data[exercise_id]
            
            if exercise_type == 'cardio':
                exercises_data.append({
                    'template_exercise_id': te.id,
                    'exercise_id': te.exercise_id,
                    'exercise_name': te.exercise.name,
                    'exercise_type': 'cardio',
                    'planned_duration': exercise_plan.get('duration', 30),
                    'planned_distance': exercise_plan.get('distance', 0),
                    'planned_heart_rate': exercise_plan.get('target_heart_rate')
                })
            else:
                # strength или bodyweight
                sets_data = []
                if exercise_plan['input_type'] == 'fixed':
                    for i in range(1, exercise_plan['sets'] + 1):
                        sets_data.append({
                            'set_number': i,
                            'planned_reps': exercise_plan['reps'],
                            'planned_weight': exercise_plan.get('weight', 0)
                        })
                else:
                    for set_info in exercise_plan['sets']:
                        sets_data.append({
                            'set_number': set_info['set_number'],
                            'planned_reps': set_info['reps'],
                            'planned_weight': set_info.get('weight', 0)
                        })
                
                exercises_data.append({
                    'template_exercise_id': te.id,
                    'exercise_id': te.exercise_id,
                    'exercise_name': te.exercise.name,
                    'exercise_type': exercise_type,
                    'sets': sets_data
                })
    
    if request.method == 'POST':
        # Сохраняем результаты
        for exercise in exercises_data:
            if exercise['exercise_type'] == 'cardio':
                # Сохраняем кардио данные как один "сет"
                actual_duration = request.form.get(f'actual_duration_{exercise["exercise_id"]}', type=int)
                actual_distance = request.form.get(f'actual_distance_{exercise["exercise_id"]}', type=float)
                actual_heart_rate = request.form.get(f'actual_heart_rate_{exercise["exercise_id"]}', type=int)
                
                # Для кардио создаём один лог подхода
                set_log = SetLog(
                    session_id=session.id,
                    exercise_id=exercise['exercise_id'],
                    set_number=1,
                    planned_reps=1,  # Условно
                    planned_weight=exercise.get('planned_duration', 0),  # Храним длительность
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
                        set_log = SetLog(
                            session_id=session.id,
                            exercise_id=exercise['exercise_id'],
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
        
        flash('Тренировка успешно сохранена!', 'success')
        return redirect(url_for('workouts.summary', session_id=session.id))
    
    return render_template('workouts/perform.html', 
                         session=session,
                         exercises_data=exercises_data)

def update_session_completion(session_id):
    """Обновляет общий процент выполнения тренировки"""
    set_logs = SetLog.query.filter_by(session_id=session_id).all()
    
    if set_logs:
        total_percent = sum(log.completion_percent for log in set_logs) / len(set_logs)
        total_tonnage = sum((log.actual_reps or 0) * (log.actual_weight or 0) for log in set_logs)
        
        session = WorkoutSession.query.get(session_id)
        session.completion_percent = round(total_percent, 1)
        session.total_tonnage = total_tonnage
        db.session.commit()
        
        # Обновляем статус расписания
        if session.schedule:
            session.schedule.status = 'completed'
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
                'exercise_type': log.exercise.exercise_type,  # <-- ДОБАВИТЬ ТИП
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
        # Создаём сессию без расписания
        session = WorkoutSession(
            user_id=current_user.id,
            schedule_id=None,
            template_id=None,
            date=datetime.utcnow(),
            status='completed'
        )
        db.session.add(session)
        db.session.commit()
        
        # Сохраняем упражнения из формы
        exercise_ids = request.form.getlist('exercise_id')
        reps_list = request.form.getlist('reps')
        weights_list = request.form.getlist('weight')
        set_numbers = request.form.getlist('set_number')
        
        for i in range(len(exercise_ids)):
            if exercise_ids[i] and reps_list[i] and weights_list[i]:
                exercise_id = int(exercise_ids[i])
                reps = int(reps_list[i])
                weight = float(weights_list[i])
                set_number = int(set_numbers[i]) if i < len(set_numbers) and set_numbers[i] else 1
                
                set_log = SetLog(
                    session_id=session.id,
                    exercise_id=exercise['exercise_id'],
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
        
        # Обновляем проценты и тоннаж
        update_session_completion(session.id)
        
        flash('Свободная тренировка сохранена!', 'success')
        return redirect(url_for('workouts.summary', session_id=session.id))
    
    # GET запрос — показываем форму
    exercises = Exercise.query.order_by(Exercise.name).all()
    return render_template('workouts/free_workout.html', exercises=exercises)

@bp.route('/save_progress/<int:session_id>', methods=['POST'])
@login_required
def save_progress(session_id):
    """Сохранение текущего прогресса тренировки (без завершения)"""
    from flask import jsonify
    
    session = WorkoutSession.query.get_or_404(session_id)
    
    if session.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    # Удаляем старые логи для этой сессии (если есть)
    SetLog.query.filter_by(session_id=session.id).delete()
    
    schedule = session.schedule
    planned_data = schedule.planned_data
    
    template_exercises = TemplateExercise.query.filter_by(template_id=schedule.template.id).order_by(TemplateExercise.order).all()
    
    completions = {}
    
    for te in template_exercises:
        exercise_id = str(te.exercise_id)
        exercise_type = te.exercise.exercise_type
        
        if exercise_id in planned_data:
            exercise_plan = planned_data[exercise_id]
            
            if exercise_type == 'cardio':
                actual_duration = request.form.get(f'actual_duration_{te.exercise_id}', type=int)
                actual_distance = request.form.get(f'actual_distance_{te.exercise_id}', type=float)
                
                if actual_duration:
                    set_log = SetLog(
                        session_id=session.id,
                        exercise_id=te.exercise_id,
                        set_number=1,
                        planned_reps=exercise_plan.get('duration', 30),
                        planned_weight=exercise_plan.get('distance', 0),
                        actual_reps=actual_duration,
                        actual_weight=actual_distance
                    )
                    set_log.calculate_completion()
                    db.session.add(set_log)
                    completions[f'{te.exercise_id}_1'] = set_log.completion_percent
                    
            else:
                # Strength или bodyweight
                if exercise_plan['input_type'] == 'fixed':
                    for i in range(1, exercise_plan['sets'] + 1):
                        actual_reps = request.form.get(f'reps_{te.exercise_id}_{i}', type=int)
                        actual_weight = request.form.get(f'weight_{te.exercise_id}_{i}', type=float)
                        
                        if actual_reps:
                            set_log = SetLog(
                                session_id=session.id,
                                exercise_id=te.exercise_id,
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
                        
                        if actual_reps:
                            set_log = SetLog(
                                session_id=session.id,
                                exercise_id=te.exercise_id,
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