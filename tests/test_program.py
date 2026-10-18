"""Шаблоны и мастер «В расписание» (план 6.4)"""
import json
from datetime import date, timedelta

from app.models import TemplateExercise, WorkoutSchedule, WorkoutTemplate
from conftest import login


def test_add_exercises_to_template(client, make_user, make_exercise):
    user = make_user('anna')
    login(client, 'anna')
    client.post('/templates/create', data={'name': 'Ноги'})
    template = WorkoutTemplate.query.filter_by(name='Ноги').one()
    ids = [make_exercise(n).id for n in ('Присед', 'Выпады')]
    client.post(f'/templates/add_exercise/{template.id}', data={'exercise_ids': ids})
    assert [te.order for te in TemplateExercise.query.filter_by(template_id=template.id).order_by(TemplateExercise.order)] == [0, 1]


def test_program_wizard_saves_cardio_parameters(client, make_user, make_exercise):
    """У кардио в мастере не было своих полей — сохранялось «30 мин, 0 км»"""
    user = make_user('anna')
    squat, bike = make_exercise('Присед'), make_exercise('Велотренажёр', 'cardio')
    template = WorkoutTemplate(name='Ноги', user_id=user.id)
    from app import db
    db.session.add(template); db.session.commit()
    te_squat = TemplateExercise(template_id=template.id, exercise_id=squat.id, order=0)
    te_bike = TemplateExercise(template_id=template.id, exercise_id=bike.id, order=1)
    db.session.add_all([te_squat, te_bike]); db.session.commit()

    login(client, 'anna')
    start = date.today()
    client.post(f'/program/create/{template.id}', data={'template_id': template.id, 'monday': 'y', 'thursday': 'y',
                                                         'start_date': start.isoformat(),
                                                         'end_date': (start + timedelta(days=13)).isoformat()})
    client.post('/program/set_parameters', data={
        f'ex_{te_squat.id}-input_type': 'progressive',
        f'progressive_data_{te_squat.id}': json.dumps([{'set_number': 1, 'weight': 60, 'reps': 10},
                                                       {'set_number': 2, 'weight': 70, 'reps': 8}]),
        f'duration_{te_bike.id}': '15', f'distance_{te_bike.id}': '6', f'heart_rate_{te_bike.id}': '140',
    })
    schedules = WorkoutSchedule.query.filter_by(template_id=template.id).all()
    assert len(schedules) == 4
    plan = schedules[0].planned_data
    assert plan[str(bike.id)]['duration'] == 15 and plan[str(bike.id)]['distance'] == 6.0
    assert [(s['weight'], s['reps']) for s in plan[str(squat.id)]['sets']] == [(60, 10), (70, 8)]


# ---------- План 3.6: проверки мастера на сервере ----------
import pytest
from app import db


@pytest.fixture
def ready_template(make_user, make_exercise, client):
    user = make_user('anna')
    template = WorkoutTemplate(name='Ноги', user_id=user.id)
    db.session.add(template); db.session.commit()
    te = TemplateExercise(template_id=template.id, exercise_id=make_exercise('Присед').id, order=0)
    db.session.add(te); db.session.commit()
    login(client, 'anna')
    return template, te


def step1(client, template, days=('monday',), start=None, end=None):
    start = start or date.today()
    end = end or start + timedelta(days=13)
    data = {'template_id': template.id, 'start_date': start.isoformat(), 'end_date': end.isoformat()}
    data.update({d: 'y' for d in days})
    return client.post(f'/program/create/{template.id}', data=data)


@pytest.mark.parametrize('kwargs, message', [
    ({'days': ()}, 'Выберите хотя бы один день'),
    ({'start': date(2026, 11, 10), 'end': date(2026, 11, 1)}, 'раньше даты начала'),
    ({'start': date(2026, 1, 1), 'end': date(2028, 1, 1)}, 'не больше года'),
])
def test_step1_rejects_bad_input(client, ready_template, kwargs, message):
    template, _ = ready_template
    response = step1(client, template, **kwargs)
    assert response.status_code == 200 and message in response.get_data(as_text=True)


@pytest.mark.parametrize('form', [
    {'-sets': '', '-reps': '10', '-weight': '40'},          # пустое поле давало ошибку 500
    {'-sets': 'abc', '-reps': '10', '-weight': '40'},
    {'-sets': '3', '-reps': '0', '-weight': '40'},
    {'-sets': '500', '-reps': '10', '-weight': '40'},
])
def test_step2_bad_numbers_do_not_crash(client, ready_template, form):
    template, te = ready_template
    step1(client, template)
    data = {f'ex_{te.id}-input_type': 'fixed', **{f'ex_{te.id}{k}': v for k, v in form.items()}}
    response = client.post('/program/set_parameters', data=data)
    assert response.status_code == 200
    assert 'Проверьте' in response.get_data(as_text=True)
    assert WorkoutSchedule.query.count() == 0


@pytest.mark.parametrize('payload', ['не json', '[]', '[{"set_number": 1}]', '[{"reps": "x", "weight": 10}]'])
def test_step2_bad_progressive_data(client, ready_template, payload):
    template, te = ready_template
    step1(client, template)
    response = client.post('/program/set_parameters', data={f'ex_{te.id}-input_type': 'progressive',
                                                            f'progressive_data_{te.id}': payload})
    assert response.status_code == 200 and WorkoutSchedule.query.count() == 0


def test_repeated_program_does_not_duplicate_dates(client, ready_template):
    template, te = ready_template
    params = {f'ex_{te.id}-input_type': 'fixed', f'ex_{te.id}-sets': '3', f'ex_{te.id}-reps': '10', f'ex_{te.id}-weight': '40'}
    for _ in range(2):
        step1(client, template, days=('monday', 'thursday'))
        client.post('/program/set_parameters', data=params)
    assert WorkoutSchedule.query.count() == 4
