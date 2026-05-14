from flask import render_template, Blueprint
from flask_login import login_required, current_user
from app import db
from app.models import WorkoutSession, SetLog

bp = Blueprint('analytics', __name__, url_prefix='/analytics')

@bp.route('/records')
@login_required
def records():
    """Мои рекорды (заглушка)"""
    return render_template('analytics/records.html')

@bp.route('/dashboard')
@login_required
def dashboard():
    """Детальная аналитика (заглушка)"""
    return render_template('analytics/dashboard.html')