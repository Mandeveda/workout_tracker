from flask import render_template, Blueprint, current_app, send_from_directory
from flask_login import login_required, current_user
from datetime import timedelta
from app.models import WorkoutSchedule, WorkoutSession
from app.timeutil import local_today, local_date, utc_start_of

bp = Blueprint('main', __name__)

WEEKDAYS_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
WEEKDAYS_FULL = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье']
MONTHS_SHORT = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
MONTHS_GENITIVE = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
                   'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']


def human_date(d):
    """«суббота, 18 октября»"""
    return f'{WEEKDAYS_FULL[d.weekday()]}, {d.day} {MONTHS_GENITIVE[d.month - 1]}'


def session_title(session):
    """Название тренировки: шаблон или «Свободная тренировка»"""
    if session.template:
        return session.template.name
    if session.schedule and session.schedule.template:
        return session.schedule.template.name
    return 'Свободная тренировка'


@bp.route('/')
def index():
    return render_template('index.html')


@bp.route('/dashboard')
@login_required
def dashboard():
    today = local_today()
    completed = WorkoutSession.query.filter_by(user_id=current_user.id, is_completed=True)

    # Незавершённая тренировка — её предлагаем продолжить в первую очередь
    active_session = WorkoutSession.query.filter_by(
        user_id=current_user.id, is_completed=False
    ).order_by(WorkoutSession.date.desc()).first()

    today_workout = WorkoutSchedule.query.filter_by(
        user_id=current_user.id, scheduled_date=today, status='planned'
    ).first()
    next_workout = None
    if not today_workout:
        next_workout = WorkoutSchedule.query.filter(
            WorkoutSchedule.user_id == current_user.id,
            WorkoutSchedule.scheduled_date > today,
            WorkoutSchedule.status == 'planned'
        ).order_by(WorkoutSchedule.scheduled_date).first()

    overdue_count = WorkoutSchedule.query.filter(
        WorkoutSchedule.user_id == current_user.id,
        WorkoutSchedule.scheduled_date < today,
        WorkoutSchedule.status == 'planned'
    ).count()

    # Текущая неделя: в какие дни тренировались и что запланировано
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    done_days = {
        local_date(s.date) for s in completed.filter(
            WorkoutSession.date >= utc_start_of(monday), WorkoutSession.date < utc_start_of(sunday + timedelta(days=1))
        ).all()
    }
    planned_days = {
        s.scheduled_date for s in WorkoutSchedule.query.filter(
            WorkoutSchedule.user_id == current_user.id,
            WorkoutSchedule.status == 'planned',
            WorkoutSchedule.scheduled_date.between(monday, sunday)
        ).all()
    }
    week = []
    for i in range(7):
        day = monday + timedelta(days=i)
        week.append({
            'short': WEEKDAYS_SHORT[i],
            'day': day.day,
            'done': day in done_days,
            'planned': day in planned_days,
            'today': day == today,
        })

    # Цифры за 30 дней и сравнение с предыдущими 30
    month_ago = today - timedelta(days=30)
    two_months_ago = today - timedelta(days=60)
    month_sessions = completed.filter(WorkoutSession.date >= utc_start_of(month_ago)).all()
    prev_month_count = completed.filter(
        WorkoutSession.date >= utc_start_of(two_months_ago), WorkoutSession.date < utc_start_of(month_ago)
    ).count()
    month_tonnage = sum(s.total_tonnage or 0 for s in month_sessions)

    past_schedules = WorkoutSchedule.query.filter(
        WorkoutSchedule.user_id == current_user.id,
        WorkoutSchedule.scheduled_date <= today
    )
    plan_total = past_schedules.count()
    plan_done = past_schedules.filter(WorkoutSchedule.status == 'completed').count()

    best_workout = completed.order_by(WorkoutSession.total_tonnage.desc()).first()

    # Тоннаж по неделям за последние 8 недель
    first_week = monday - timedelta(weeks=7)
    weekly = {first_week + timedelta(weeks=i): 0 for i in range(8)}
    for s in completed.filter(WorkoutSession.date >= utc_start_of(first_week)).all():
        day = local_date(s.date)
        week_start = day - timedelta(days=day.weekday())
        if week_start in weekly:
            weekly[week_start] += s.total_tonnage or 0
    chart = {
        'labels': [d.strftime('%d.%m') for d in weekly],
        'values': [round(v) for v in weekly.values()],
    }

    recent = completed.order_by(WorkoutSession.date.desc()).limit(4).all()

    return render_template(
        'dashboard.html',
        today_text=human_date(today),
        active_session=active_session,
        today_workout=today_workout,
        next_workout=next_workout,
        next_workout_text=human_date(next_workout.scheduled_date) if next_workout else None,
        week=week,
        overdue_count=overdue_count,
        month_count=len(month_sessions),
        month_delta=len(month_sessions) - prev_month_count,
        month_tonnage=month_tonnage,
        month_avg=month_tonnage / len(month_sessions) if month_sessions else 0,
        plan_total=plan_total,
        plan_done=plan_done,
        plan_percent=round(plan_done / plan_total * 100) if plan_total else None,
        best_workout=best_workout,
        chart=chart,
        recent=recent,
        session_title=session_title,
        months_short=MONTHS_SHORT,
    )


@bp.route('/offline')
def offline():
    """Страница «Нет соединения». Кэшируется service worker'ом, поэтому без данных пользователя"""
    return render_template('offline.html')


@bp.route('/sw.js')
def service_worker():
    """Service worker с корня сайта — только так он управляет всеми страницами (а не только /static/)"""
    response = send_from_directory(current_app.static_folder, 'sw.js', mimetype='application/javascript', max_age=0)
    response.headers['Cache-Control'] = 'no-cache'
    return response
