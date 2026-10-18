"""Тренировки: свободная, по плану, сохранение отметок (план 1.1, 6.4)"""
import pytest

from app import db
from app.models import SetLog, WorkoutSession
from conftest import login

STRENGTH_PLAN = {'input_type': 'fixed', 'sets': 3, 'reps': 8, 'weight': 60}


@pytest.fixture
def planned(make_user, make_exercise, make_template, make_session):
    user = make_user('anna')
    squat = make_exercise('Приседания')
    template, schedule = make_template(user, [(squat, STRENGTH_PLAN)])
    session = make_session(user, schedule, logs=[(squat, 8, 60), (squat, 8, 60)])
    return user, squat, session


def test_free_workout_never_touches_scheduled_session(client, planned):
    """План 1.1: свободная тренировка удаляла подходы незавершённой тренировки по плану"""
    user, squat, scheduled = planned
    login(client, 'anna')
    page = client.get('/workouts/free_workout').get_data(as_text=True)
    assert f'session_id={scheduled.id}' not in page
    client.post(f'/workouts/free_workout?session_id={scheduled.id}',
                data={'exercise_id[]': [squat.id], 'set_number[]': [1], 'weight[]': [20], 'reps[]': [5]})
    assert SetLog.query.filter_by(session_id=scheduled.id).count() == 2
    assert WorkoutSession.query.filter_by(schedule_id=None).count() == 1


def test_continue_link_points_to_right_page(client, planned):
    _, _, scheduled = planned
    login(client, 'anna')
    page = client.get('/workouts/').get_data(as_text=True)
    assert f'/workouts/perform/{scheduled.id}' in page


def test_save_progress_deletes_unchecked_sets(client, planned):
    _, squat, session = planned
    login(client, 'anna')
    client.post(f'/workouts/save_progress/{session.id}', data={f'weight_{squat.id}_1': '60', f'reps_{squat.id}_1': '8'})
    assert SetLog.query.filter_by(session_id=session.id).count() == 1
    client.post(f'/workouts/save_progress/{session.id}', data={})
    db.session.refresh(session)
    assert SetLog.query.filter_by(session_id=session.id).count() == 0
    assert session.completion_percent == 0 and session.total_tonnage == 0


def test_complete_workout(client, planned):
    _, _, session = planned
    login(client, 'anna')
    response = client.post(f'/workouts/complete/{session.id}').get_json()
    assert response['success'] and response['redirect'].endswith(f'/summary/{session.id}')
    db.session.refresh(session)
    assert session.is_completed and session.schedule.status == 'completed'


def test_free_workout_ajax_save_keeps_order_and_cardio_fields(client, make_user, make_exercise):
    make_user('anna')
    bench = make_exercise('Жим')
    run = make_exercise('Бег', 'cardio')
    login(client, 'anna')
    result = client.post('/workouts/free_workout', headers={'X-Requested-With': 'fetch'},
                         data={'action': 'save', 'exercise_id[]': [run.id, bench.id], 'set_number[]': [1, 1],
                               'weight[]': [5, 60], 'reps[]': [30, 8]}).get_json()
    assert result['success'] and result['saved'] == 2
    logs = SetLog.query.filter_by(session_id=result['session_id']).order_by(SetLog.id).all()
    assert [l.exercise_id for l in logs] == [run.id, bench.id]
    assert (logs[0].actual_reps, logs[0].actual_weight) == (30, 5)   # минуты в reps, км в weight


# ---------- План 3.7: единый путь сохранения тренировки по плану ----------
@pytest.fixture
def mixed(make_user, make_exercise, make_template, make_session):
    user = make_user('anna', weight=80)
    squat = make_exercise('Присед')
    pullup = make_exercise('Подтягивания', 'bodyweight')
    bike = make_exercise('Велотренажёр', 'cardio')
    plans = [(squat, STRENGTH_PLAN),
             (pullup, {'input_type': 'progressive', 'sets': [{'set_number': 1, 'reps': 10, 'weight': 0},
                                                             {'set_number': 2, 'reps': 8, 'weight': 0}]}),
             (bike, {'input_type': 'cardio', 'duration': 20, 'distance': 5})]
    _, schedule = make_template(user, plans)
    return user, squat, pullup, bike, make_session(user, schedule)


def test_save_progress_all_exercise_types(client, mixed):
    user, squat, pullup, bike, session = mixed
    login(client, 'anna')
    result = client.post(f'/workouts/save_progress/{session.id}', data={
        f'weight_{squat.id}_1': '60', f'reps_{squat.id}_1': '8',        # 100%
        f'reps_{pullup.id}_2': '4',                                       # 4 из 8 = 50%
        f'actual_duration_{bike.id}': '10', f'actual_distance_{bike.id}': '3',   # 10 из 20 мин = 50%
    }).get_json()
    assert result['completions'] == {f'{squat.id}_1': 100, f'{pullup.id}_2': 50, f'{bike.id}_1': 50}
    logs = {(l.exercise_id, l.set_number): l for l in SetLog.query.filter_by(session_id=session.id)}
    assert (logs[(bike.id, 1)].actual_reps, logs[(bike.id, 1)].actual_weight) == (10, 3)
    assert logs[(pullup.id, 2)].planned_reps == 8 and logs[(squat.id, 1)].template_exercise_id is not None


def test_save_progress_updates_existing_set(client, mixed):
    user, squat, _, _, session = mixed
    login(client, 'anna')
    for reps in ('8', '6'):
        client.post(f'/workouts/save_progress/{session.id}', data={f'weight_{squat.id}_1': '60', f'reps_{squat.id}_1': reps})
    logs = SetLog.query.filter_by(session_id=session.id).all()
    assert len(logs) == 1 and logs[0].actual_reps == 6 and round(logs[0].completion_percent) == 75


def test_perform_accepts_only_get(client, mixed):
    *_, session = mixed
    login(client, 'anna')
    assert client.get(f'/workouts/perform/{session.id}').status_code == 200
    assert client.post(f'/workouts/perform/{session.id}').status_code == 405
