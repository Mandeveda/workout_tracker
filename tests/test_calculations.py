"""Этап 3 плана: расчёты"""
import pytest

from app import db
from app.models import SetLog, TemplateExercise
from app.routes.workouts import update_session_completion

SQUAT_PLAN = {'input_type': 'fixed', 'sets': 3, 'reps': 8, 'weight': 80}
PULLUP_PLAN = {'input_type': 'progressive', 'sets': [{'set_number': 1, 'reps': 10, 'weight': 0},
                                                     {'set_number': 2, 'reps': 8, 'weight': 0}]}
BIKE_PLAN = {'input_type': 'cardio', 'duration': 20, 'distance': 5}


@pytest.fixture
def plan(make_user, make_exercise, make_template):
    user = make_user('anna', weight=80)
    squat = make_exercise('Приседания')
    pullup = make_exercise('Подтягивания', 'bodyweight')
    bike = make_exercise('Велотренажёр', 'cardio')
    template, schedule = make_template(user, [(squat, SQUAT_PLAN), (pullup, PULLUP_PLAN), (bike, BIKE_PLAN)])
    return user, schedule, squat, pullup, bike


def add_log(session, exercise, n, planned, actual, user_weight=80):
    log = SetLog(session_id=session.id, exercise_id=exercise.id, set_number=n,
                 planned_reps=planned[0], planned_weight=planned[1], actual_reps=actual[0], actual_weight=actual[1])
    log.calculate_completion(user_weight)
    db.session.add(log)
    db.session.commit()


def test_completion_counts_unmarked_planned_sets(plan, make_session):
    """План 3.1: 1 из 10 подходов не должно давать 100% — считаем от запланированных"""
    user, schedule, squat, _, _ = plan
    session = make_session(user, schedule)
    add_log(session, squat, 1, (8, 80), (8, 80))     # 100%
    add_log(session, squat, 2, (8, 80), (4, 80))     # 50%
    update_session_completion(session.id)
    assert session.completion_percent == 25.0         # (100 + 50) / 6 запланированных подходов


def test_completion_all_planned_sets_done(plan, make_session):
    user, schedule, squat, pullup, bike = plan
    session = make_session(user, schedule)
    for n in (1, 2, 3):
        add_log(session, squat, n, (8, 80), (8, 80))
    add_log(session, pullup, 1, (10, 0), (10, 0))
    add_log(session, pullup, 2, (8, 0), (8, 0))
    add_log(session, bike, 1, (20, 5), (20, 5))
    update_session_completion(session.id)
    assert session.completion_percent == 100.0


def test_completion_ignores_plan_entries_removed_from_template(plan, make_session):
    """Упражнение убрали из шаблона — на экране тренировки его нет, в процент оно не входит"""
    user, schedule, squat, pullup, bike = plan
    TemplateExercise.query.filter(TemplateExercise.exercise_id.in_([pullup.id, bike.id])).delete()
    db.session.commit()
    session = make_session(user, schedule)
    for n in (1, 2, 3):
        add_log(session, squat, n, (8, 80), (8, 80))
    update_session_completion(session.id)
    assert session.completion_percent == 100.0


def test_free_workout_completion_is_average_of_logged_sets(make_user, make_exercise, make_session):
    user = make_user('anna')
    session = make_session(user, logs=[(make_exercise('Жим'), 8, 60), (make_exercise('Тяга'), 10, 50)])
    update_session_completion(session.id)
    assert session.completion_percent == 100.0


def test_summary_exercise_percent_matches_planned_sets(client, plan, make_session):
    user, schedule, squat, _, _ = plan
    session = make_session(user, schedule)
    add_log(session, squat, 1, (8, 80), (8, 80))
    update_session_completion(session.id)
    client.post('/auth/login', data={'username': 'anna', 'password': 'pass123'})
    page = client.get(f'/workouts/summary/{session.id}').get_data(as_text=True)
    assert '33%' in page            # приседания: 1 из 3 подходов
    assert '1 из 3' in page


def test_recalc_keeps_totals_of_sessions_without_logs(make_user, make_session, capsys):
    """У старых тренировок подходы могли быть потеряны — их сохранённый итог пересчёт не стирает"""
    from recalc_stats import recalc
    user = make_user('anna')
    lost = make_session(user, completed=True)
    lost.completion_percent, lost.total_tonnage = 100, 2025
    db.session.commit()
    recalc(apply_changes=True)
    db.session.refresh(lost)
    assert (lost.completion_percent, lost.total_tonnage) == (100, 2025)
    assert 'итог оставлен как есть: 1' in capsys.readouterr().out


def test_tonnage_counts_only_strength(plan, make_session):
    """План 3.2: кардио добавляло в тоннаж «минуты × км»; собственный вес в тоннаж не входит (решение владельца)"""
    user, schedule, squat, pullup, bike = plan
    session = make_session(user, schedule)
    add_log(session, squat, 1, (8, 80), (8, 80))      # 640 кг
    add_log(session, pullup, 1, (10, 0), (10, 0))
    add_log(session, bike, 1, (20, 5), (20, 5))       # было бы +100 «кг»
    update_session_completion(session.id)
    assert session.total_tonnage == 640
