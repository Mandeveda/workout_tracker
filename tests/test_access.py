"""Права доступа и защита от изменения данных по ссылке (план 2.1, 2.2)"""
import pytest

from app import db
from app.models import TemplateExercise, WorkoutTemplate
from conftest import login, csrf_token


@pytest.fixture
def two_users(make_user, make_exercise, make_template):
    owner = make_user('owner')
    other = make_user('other')
    squat = make_exercise('Приседания')
    template, schedule = make_template(owner, [(squat, {'input_type': 'fixed', 'sets': 3, 'reps': 8, 'weight': 60})])
    return owner, other, template, schedule


@pytest.mark.parametrize('url', [
    '/templates/delete/{t}', '/templates/archive/{t}', '/templates/restore/{t}',
    '/workouts/skip/{s}', '/workouts/postpone/{s}', '/workouts/delete_schedule/{s}',
])
def test_state_changing_routes_reject_get(client, two_users, url):
    owner, _, template, schedule = two_users
    login(client, 'owner')
    assert client.get(url.format(t=template.id, s=schedule.id)).status_code == 405


def test_post_without_csrf_token_is_rejected(client, two_users, csrf_app):
    owner, _, template, schedule = two_users
    token = csrf_token(client)
    client.post('/auth/login', data={'username': 'owner', 'password': 'pass123', 'csrf_token': token})
    assert client.post(f'/workouts/skip/{schedule.id}').status_code == 400


def test_other_user_cannot_edit_template(client, two_users):
    _, other, template, _ = two_users
    login(client, 'other')
    client.post(f'/templates/edit/{template.id}', data={'edit_name': '1', 'name': 'Взломано'})
    client.post(f'/templates/delete/{template.id}')
    assert db.session.get(WorkoutTemplate, template.id).name == 'День ног'


def test_move_exercise_ignores_foreign_template_id_in_url(client, two_users, make_exercise, make_template):
    """План 2.2: своё упражнение + чужой template_id в адресе не меняет порядок в чужом шаблоне"""
    owner, other, victim_template, _ = two_users
    db.session.add(TemplateExercise(template_id=victim_template.id, exercise_id=make_exercise('Выпады').id, order=1))
    db.session.commit()
    own_template, _ = make_template(other, [(make_exercise('Жим'), {})], name='Свой')
    own_item = TemplateExercise.query.filter_by(template_id=own_template.id).first()
    own_item.order = 5
    db.session.commit()

    login(client, 'other')
    client.post(f'/templates/move_up/{victim_template.id}/{own_item.id}')
    orders = [te.order for te in TemplateExercise.query.filter_by(template_id=victim_template.id).order_by(TemplateExercise.id)]
    assert orders == [0, 1]


def test_other_user_cannot_open_foreign_workout(client, two_users, make_session):
    owner, _, _, schedule = two_users
    session = make_session(owner, schedule)
    login(client, 'other')
    for url in (f'/workouts/perform/{session.id}', f'/workouts/summary/{session.id}'):
        response = client.get(url)
        assert response.status_code == 302 and '/workouts' in response.headers['Location']
    assert client.post(f'/workouts/save_progress/{session.id}').status_code == 403


def test_admin_pages_require_admin(client, make_user):
    make_user('plain')
    login(client, 'plain')
    assert client.get('/admin/users').status_code == 302


def test_only_experts_add_exercises(client, make_user):
    make_user('plain')
    make_user('expert', role_id=3)
    login(client, 'plain')
    assert client.get('/exercises/add').status_code == 302
    client.post('/auth/logout')
    login(client, 'expert')
    assert client.get('/exercises/add').status_code == 200
