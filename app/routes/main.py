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
    
    today_workout = WorkoutSchedule.query.filter_by(
        user_id=current_user.id,
        scheduled_date=today,
        status='planned'
    ).first()
    
    recent_workouts = WorkoutSession.query.filter_by(
        user_id=current_user.id
    ).order_by(WorkoutSession.date.desc()).limit(5).all()
    
    total_workouts = WorkoutSession.query.filter_by(user_id=current_user.id).count()
    completed_plan = WorkoutSchedule.query.filter_by(
        user_id=current_user.id, 
        status='completed'
    ).count()
    
    best_tonnage = 0
    pr_count = 0
    plan_completion_percent = 0
    
    if completed_plan > 0:
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
        best_tonnage=best_tonnage,
        pr_count=pr_count
    )