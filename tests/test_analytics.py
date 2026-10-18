"""Аналитика и главная: только завершённые тренировки, тип упражнения (план 3.3, 3.4)"""
from conftest import login


def test_unfinished_workouts_not_in_records_and_progress(client, make_user, make_exercise, make_session):
    user = make_user('anna')
    squat = make_exercise('Приседания')
    make_session(user, completed=True, days_ago=3, logs=[(squat, 8, 80)])
    make_session(user, completed=False, logs=[(squat, 1, 500)])
    login(client, 'anna')
    records = client.get('/analytics/records').get_data(as_text=True)
    assert '80,0 кг' in records and '500,0 кг' not in records
    data = client.get(f'/analytics/progress_data/{squat.id}').get_json()
    assert max(data['series']['weight']) == 80
    assert len(client.get('/analytics/calendar_data').get_json()) == 1


def test_cardio_records_use_minutes_and_km(client, make_user, make_exercise, make_session):
    user = make_user('anna')
    run = make_exercise('Бег', 'cardio')
    make_session(user, completed=True, logs=[(run, 30, 5)])
    login(client, 'anna')
    page = client.get('/analytics/records').get_data(as_text=True)
    assert 'Дальше всего' in page and 'Макс. вес' not in page
    assert client.get(f'/analytics/progress_data/{run.id}').get_json()['type'] == 'cardio'


def test_pages_open_for_new_user(client, make_user):
    make_user('anna')
    login(client, 'anna')
    for url in ('/dashboard', '/workouts/', '/workouts/free_workout', '/templates/', '/exercises/',
                '/analytics/dashboard', '/analytics/records', '/analytics/progress', '/analytics/calendar', '/profile/'):
        assert client.get(url).status_code == 200, url
