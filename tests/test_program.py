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
