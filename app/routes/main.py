from flask import render_template, Blueprint
from flask_login import login_required, current_user
from datetime import datetime
from app.models import WorkoutSchedule, WorkoutSession

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    return render_template('index.html')

@bp.route('/dashboard')
@login_required
def dashboard():
    today = datetime.utcnow().date()
    
    # Тренировка на сегодня
    today_workout = WorkoutSchedule.query.filter_by(
        user_id=current_user.id,
        scheduled_date=today,
        status='planned'
    ).first()
    
    # Последние 5 тренировок
    recent_workouts = WorkoutSession.query.filter_by(
        user_id=current_user.id
    ).order_by(WorkoutSession.date.desc()).limit(5).all()
    
    # Статистика
    total_workouts = WorkoutSession.query.filter_by(user_id=current_user.id).count()
    completed_plan = WorkoutSchedule.query.filter_by(
        user_id=current_user.id, 
        status='completed'
    ).count()
    
    # Лучший тоннаж (из всех тренировок)
    best_workout = WorkoutSession.query.filter_by(user_id=current_user.id).order_by(WorkoutSession.total_tonnage.desc()).first()
    best_tonnage = best_workout.total_tonnage if best_workout else 0
    
    # Количество рекордов (пока заглушка, потом реализуем)
    pr_count = 0
    
    # Процент выполнения плана
    plan_completion_percent = 0
    total_planned = WorkoutSchedule.query.filter_by(user_id=current_user.id).count()
    if total_planned > 0:
        plan_completion_percent = round((completed_plan / total_planned) * 100)
    
    return render_template(
        'dashboard.html',
        user=current_user,
        today_date=today.strftime('%d.%m.%Y'),
        today_workout=today_workout,
        recent_workouts=recent_workouts,
        total_workouts=total_workouts,
        completed_plan=completed_plan,
        plan_completion_percent=plan_completion_percent,
        best_tonnage=round(best_tonnage, 1),
        pr_count=pr_count
    )