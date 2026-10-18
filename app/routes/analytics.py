from flask import render_template, Blueprint, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import WorkoutSession, SetLog, Exercise
from app.routes.main import MONTHS_SHORT
from datetime import datetime, timedelta

bp = Blueprint('analytics', __name__, url_prefix='/analytics')


def completed_logs(exercise_id=None):
    """Подходы текущего пользователя только из завершённых тренировок"""
    query = SetLog.query.join(WorkoutSession).filter(
        WorkoutSession.user_id == current_user.id,
        WorkoutSession.is_completed.is_(True),
        SetLog.actual_reps.isnot(None),
    )
    if exercise_id is not None:
        query = query.filter(SetLog.exercise_id == exercise_id)
    return query


def user_exercises():
    """Упражнения, которые пользователь выполнял в завершённых тренировках"""
    ids = [row[0] for row in completed_logs().with_entities(SetLog.exercise_id).distinct()]
    return Exercise.query.filter(Exercise.id.in_(ids)).order_by(Exercise.name).all() if ids else []


def exercise_records(exercise):
    """Личные рекорды по упражнению с учётом его типа.

    Для кардио в SetLog минуты лежат в actual_reps, километры — в actual_weight.
    """
    logs = completed_logs(exercise.id).all()
    if not logs:
        return None

    def best(score, value):
        """Подход с наибольшим score; None, если значение рекорда нулевое"""
        top = max(logs, key=score)
        return top if value(top) > 0 else None

    w = lambda l: l.actual_weight or 0
    r = lambda l: l.actual_reps or 0

    if exercise.exercise_type == 'cardio':
        return {
            'longest': best(lambda l: (r(l), w(l)), r),
            'farthest': best(lambda l: (w(l), r(l)), w),
        }
    if exercise.exercise_type == 'bodyweight':
        return {'max_reps': best(lambda l: r(l), r)}
    return {
        'max_weight': best(lambda l: (w(l), r(l)), w),      # больший вес, при равном — больше повторений
        'max_reps': best(lambda l: (r(l), w(l)), r),
        'max_set': best(lambda l: w(l) * r(l), lambda l: w(l) * r(l)),
    }


@bp.route('/records')
@login_required
def records():
    """Личные рекорды по упражнениям"""
    records = []
    for exercise in user_exercises():
        rec = exercise_records(exercise)
        if rec:
            records.append({'exercise': exercise, **rec})
    return render_template('analytics/records.html', records=records)


@bp.route('/progress')
@login_required
def progress():
    """Прогресс по упражнениям (графики)"""
    return render_template('analytics/progress.html', exercises=user_exercises())


@bp.route('/progress_data/<int:exercise_id>')
@login_required
def progress_data(exercise_id):
    """Лучшие значения по датам для графика прогресса (JSON).

    a — основная величина (вес, повторения или минуты), b — дополнительная
    (повторения или километры), set — лучший тоннаж подхода (только силовые).
    """
    exercise = db.session.get(Exercise, exercise_id)
    if not exercise:
        return jsonify({'error': 'Exercise not found'}), 404

    by_date = {}
    for log in completed_logs(exercise_id).order_by(WorkoutSession.date).all():
        day = log.session.date.strftime('%Y-%m-%d')
        point = by_date.setdefault(day, {'weight': 0, 'reps': 0, 'set': 0, 'minutes': 0, 'km': 0})
        weight, reps = log.actual_weight or 0, log.actual_reps or 0
        point['weight'] = max(point['weight'], weight)
        point['reps'] = max(point['reps'], reps)
        point['set'] = max(point['set'], weight * reps)
        point['minutes'] = max(point['minutes'], reps)
        point['km'] = max(point['km'], weight)

    days = sorted(by_date)
    return jsonify({
        'type': exercise.exercise_type,
        'dates': [datetime.strptime(d, '%Y-%m-%d').strftime('%d.%m.%y') for d in days],
        'series': {key: [round(by_date[d][key], 1) for d in days] for key in ('weight', 'reps', 'set', 'minutes', 'km')},
    })


@bp.route('/dashboard')
@login_required
def dashboard():
    """Обзор: цифры за 30 дней, тоннаж по неделям, упражнения по объёму"""
    today = datetime.utcnow().date()
    month_ago = today - timedelta(days=30)
    completed = WorkoutSession.query.filter_by(user_id=current_user.id, is_completed=True)
    month_sessions = completed.filter(WorkoutSession.date >= month_ago).all()

    workouts_last_month = len(month_sessions)
    total_tonnage = sum(s.total_tonnage or 0 for s in month_sessions)
    avg_completion = (sum(s.completion_percent or 0 for s in month_sessions) / workouts_last_month
                      if workouts_last_month else None)

    # Рекорды, поставленные за 30 дней: лучший подход упражнения сделан в этот период
    fresh_records = []
    for exercise in user_exercises():
        rec = exercise_records(exercise) or {}
        main = rec.get('max_weight') or rec.get('max_reps') or rec.get('farthest') or rec.get('longest')
        if main and main.session.date.date() >= month_ago:
            fresh_records.append({'exercise': exercise, 'log': main})

    best_workout = completed.order_by(WorkoutSession.total_tonnage.desc()).first()

    # Тоннаж по неделям за 12 недель
    monday = today - timedelta(days=today.weekday())
    first_week = monday - timedelta(weeks=11)
    weekly = {first_week + timedelta(weeks=i): 0 for i in range(12)}
    for s in completed.filter(WorkoutSession.date >= first_week).all():
        start = s.date.date() - timedelta(days=s.date.weekday())
        if start in weekly:
            weekly[start] += s.total_tonnage or 0
    chart = {'labels': [d.strftime('%d.%m') for d in weekly], 'values': [round(v) for v in weekly.values()]}

    # Упражнения по объёму за 30 дней (силовые — тоннаж, остальные — число подходов)
    volume = {}
    for log in completed_logs().filter(WorkoutSession.date >= month_ago).all():
        item = volume.setdefault(log.exercise_id, {'exercise': log.exercise, 'sets': 0, 'tonnage': 0})
        item['sets'] += 1
        if log.exercise.exercise_type == 'strength':
            item['tonnage'] += (log.actual_weight or 0) * (log.actual_reps or 0)
    top_exercises = sorted(volume.values(), key=lambda i: (i['tonnage'], i['sets']), reverse=True)[:6]

    return render_template('analytics/dashboard.html',
                           workouts_last_month=workouts_last_month,
                           total_tonnage=total_tonnage,
                           avg_completion=avg_completion,
                           fresh_records=fresh_records,
                           best_workout=best_workout,
                           chart=chart,
                           top_exercises=top_exercises)


@bp.route('/calendar')
@login_required
def calendar():
    """Календарь активности за полгода"""
    return render_template('analytics/calendar.html', months_short=MONTHS_SHORT)


@bp.route('/calendar_data')
@login_required
def calendar_data():
    """Тренировки по дням за последние 6 месяцев (JSON), только завершённые"""
    start_date = datetime.utcnow().date() - timedelta(days=183)
    sessions = WorkoutSession.query.filter(
        WorkoutSession.user_id == current_user.id,
        WorkoutSession.is_completed.is_(True),
        WorkoutSession.date >= start_date
    ).all()

    data = {}
    for session in sessions:
        day = data.setdefault(session.date.strftime('%Y-%m-%d'), {'count': 0, 'total_tonnage': 0})
        day['count'] += 1
        day['total_tonnage'] += session.total_tonnage or 0
    return jsonify(data)
