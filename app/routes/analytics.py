from flask import render_template, Blueprint, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import WorkoutSession, SetLog, Exercise
from sqlalchemy import func
from datetime import datetime, timedelta

bp = Blueprint('analytics', __name__, url_prefix='/analytics')

@bp.route('/records')
@login_required
def records():
    """Мои рекорды по упражнениям"""
    
    # Получаем все уникальные упражнения, которые выполнял пользователь
    exercises_with_logs = db.session.query(SetLog.exercise_id).filter(
        SetLog.session.has(user_id=current_user.id)
    ).distinct().all()
    
    exercise_ids = [ex[0] for ex in exercises_with_logs]
    exercises = Exercise.query.filter(Exercise.id.in_(exercise_ids)).all()
    
    records = []
    
    for exercise in exercises:
        # Получаем лучший вес при максимальных повторениях
        best_by_weight = SetLog.query.filter(
            SetLog.session.has(user_id=current_user.id),
            SetLog.exercise_id == exercise.id,
            SetLog.actual_weight.isnot(None),
            SetLog.actual_reps.isnot(None)
        ).order_by(
            SetLog.actual_weight.desc(),
            SetLog.actual_reps.desc()
        ).first()
        
        # Получаем максимальное количество повторений при любом весе
        best_by_reps = SetLog.query.filter(
            SetLog.session.has(user_id=current_user.id),
            SetLog.exercise_id == exercise.id,
            SetLog.actual_reps.isnot(None)
        ).order_by(
            SetLog.actual_reps.desc(),
            SetLog.actual_weight.desc()
        ).first()
        
        # Получаем максимальный тоннаж за один подход
        best_tonnage_set = None
        max_tonnage = 0
        all_sets = SetLog.query.filter(
            SetLog.session.has(user_id=current_user.id),
            SetLog.exercise_id == exercise.id,
            SetLog.actual_weight.isnot(None),
            SetLog.actual_reps.isnot(None)
        ).all()
        
        for set_log in all_sets:
            tonnage = (set_log.actual_weight or 0) * (set_log.actual_reps or 0)
            if tonnage > max_tonnage:
                max_tonnage = tonnage
                best_tonnage_set = set_log
        
        if best_by_weight or best_by_reps:
            records.append({
                'exercise': exercise,
                'best_weight': best_by_weight,
                'best_reps': best_by_reps,
                'best_tonnage': best_tonnage_set,
                'max_tonnage': max_tonnage
            })
    
    records.sort(key=lambda x: x['exercise'].name)
    
    return render_template('analytics/records.html', records=records)

@bp.route('/progress')
@login_required
def progress():
    """Прогресс по упражнениям (графики)"""
    exercises_with_logs = db.session.query(SetLog.exercise_id).filter(
        SetLog.session.has(user_id=current_user.id)
    ).distinct().all()
    
    exercise_ids = [ex[0] for ex in exercises_with_logs]
    exercises = Exercise.query.filter(Exercise.id.in_(exercise_ids)).order_by(Exercise.name).all()
    
    return render_template('analytics/progress.html', exercises=exercises)

@bp.route('/progress_data/<int:exercise_id>')
@login_required
def progress_data(exercise_id):
    """Данные для графика прогресса (JSON)"""
    
    # Проверяем, что упражнение существует
    exercise = Exercise.query.get(exercise_id)
    if not exercise:
        return jsonify({'error': 'Exercise not found'}), 404
    
    # Получаем все подходы по упражнению с правильной сортировкой по дате
    set_logs = SetLog.query.filter(
        SetLog.session.has(user_id=current_user.id),
        SetLog.exercise_id == exercise_id,
        SetLog.actual_weight.isnot(None),
        SetLog.actual_reps.isnot(None)
    ).join(WorkoutSession).order_by(WorkoutSession.date).all()
    
    if not set_logs:
        return jsonify({'dates': [], 'weights': [], 'reps': [], 'tonnage': []})
    
    # Группируем по датам тренировок
    data_by_date = {}
    for log in set_logs:
        date_str = log.session.date.strftime('%Y-%m-%d')
        if date_str not in data_by_date:
            data_by_date[date_str] = {
                'max_weight': 0,
                'max_reps': 0,
                'max_tonnage': 0,
                'date': date_str
            }
        
        tonnage = (log.actual_weight or 0) * (log.actual_reps or 0)
        
        if (log.actual_weight or 0) > data_by_date[date_str]['max_weight']:
            data_by_date[date_str]['max_weight'] = log.actual_weight or 0
        
        if (log.actual_reps or 0) > data_by_date[date_str]['max_reps']:
            data_by_date[date_str]['max_reps'] = log.actual_reps or 0
        
        if tonnage > data_by_date[date_str]['max_tonnage']:
            data_by_date[date_str]['max_tonnage'] = tonnage
    
    sorted_data = sorted(data_by_date.values(), key=lambda x: x['date'])
    
    return jsonify({
        'dates': [d['date'] for d in sorted_data],
        'weights': [d['max_weight'] for d in sorted_data],
        'reps': [d['max_reps'] for d in sorted_data],
        'tonnage': [round(d['max_tonnage'], 1) for d in sorted_data]
    })

@bp.route('/dashboard')
@login_required
def dashboard():
    """Детальная аналитика (сводная статистика)"""
    
    thirty_days_ago = datetime.utcnow().date() - timedelta(days=30)
    
    # Количество тренировок за месяц
    workouts_last_month = WorkoutSession.query.filter(
        WorkoutSession.user_id == current_user.id,
        WorkoutSession.date >= thirty_days_ago
    ).count()
    
    # Общий тоннаж за месяц
    total_tonnage = db.session.query(func.sum(WorkoutSession.total_tonnage)).filter(
        WorkoutSession.user_id == current_user.id,
        WorkoutSession.date >= thirty_days_ago
    ).scalar() or 0
    
    # Количество рекордов
    exercises_count = db.session.query(SetLog.exercise_id).filter(
        SetLog.session.has(user_id=current_user.id)
    ).distinct().count()
    records_count = exercises_count * 2
    
    # Лучшая тренировка по тоннажу
    best_workout = WorkoutSession.query.filter_by(user_id=current_user.id).order_by(WorkoutSession.total_tonnage.desc()).first()
    
    return render_template('analytics/dashboard.html',
                         workouts_last_month=workouts_last_month,
                         total_tonnage=round(total_tonnage, 1),
                         records_count=records_count,
                         best_workout=best_workout)

@bp.route('/calendar')
@login_required
def calendar():
    """Календарь активности (heatmap)"""
    return render_template('analytics/calendar.html')

@bp.route('/calendar_data')
@login_required
def calendar_data():
    """Данные для календаря активности (JSON)"""
    from datetime import datetime, timedelta
    
    # Данные за последние 6 месяцев
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=180)
    
    # Получаем все тренировки пользователя за период
    sessions = WorkoutSession.query.filter(
        WorkoutSession.user_id == current_user.id,
        WorkoutSession.date >= start_date
    ).all()
    
    # Группируем по датам
    data = {}
    for session in sessions:
        date_str = session.date.strftime('%Y-%m-%d')
        if date_str not in data:
            data[date_str] = {
                'count': 0,
                'total_tonnage': 0
            }
        data[date_str]['count'] += 1
        data[date_str]['total_tonnage'] += session.total_tonnage or 0
    
    return jsonify(data)