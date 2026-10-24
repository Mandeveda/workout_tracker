"""Админка: отметка «был на сайте», фильтр шаблонов по владельцу"""
from datetime import datetime, timedelta
from unittest import mock

from app import db
from app.models import User, WorkoutTemplate
from tests.conftest import login


def test_last_seen_is_updated_at_most_every_5_minutes(client, make_user):
    user = make_user('ivan')
    login(client, 'ivan')
    client.get('/dashboard')
    db.session.refresh(user)
    first = user.last_seen_at
    assert first is not None

    with mock.patch('app.timeutil.utcnow', return_value=first + timedelta(minutes=2)):
        client.get('/dashboard')
    db.session.refresh(user)
    assert user.last_seen_at == first                  # чаще 5 минут не пишем

    later = first + timedelta(minutes=6)
    with mock.patch('app.timeutil.utcnow', return_value=later):
        client.get('/dashboard')
    db.session.refresh(user)
    assert user.last_seen_at == later


def test_admin_sees_last_seen(client, make_user):
    make_user('boss', role_id=1)
    make_user('ivan', last_seen_at=datetime(2026, 3, 5, 10, 0))
    make_user('ghost')
    login(client, 'boss')
    page = client.get('/admin/users').get_data(as_text=True)
    assert 'был(а) 05.03.2026' in page and 'ещё не заходил(а)' in page and 'был(а) сегодня в' in page


def test_admin_filters_templates_by_owner(client, make_user):
    make_user('boss', role_id=1)
    ivan, petr = make_user('ivan'), make_user('petr')
    db.session.add_all([WorkoutTemplate(name='Спина Ивана', user_id=ivan.id),
                        WorkoutTemplate(name='Ноги Петра', user_id=petr.id)])
    db.session.commit()
    login(client, 'boss')
    everything = client.get('/templates/').get_data(as_text=True)
    assert 'Спина Ивана' in everything and 'Ноги Петра' in everything and 'Все пользователи · 2' in everything
    only_ivan = client.get(f'/templates/?owner={ivan.id}').get_data(as_text=True)
    assert 'Спина Ивана' in only_ivan and 'Ноги Петра' not in only_ivan
    unknown = client.get('/templates/?owner=999').get_data(as_text=True)
    assert 'Ноги Петра' in unknown                      # неизвестный владелец — показываем всех


def test_user_does_not_see_owner_filter(client, make_user):
    ivan = make_user('ivan')
    petr = make_user('petr')
    db.session.add_all([WorkoutTemplate(name='Спина Ивана', user_id=ivan.id),
                        WorkoutTemplate(name='Ноги Петра', user_id=petr.id)])
    db.session.commit()
    login(client, 'ivan')
    page = client.get(f'/templates/?owner={petr.id}').get_data(as_text=True)
    assert 'Ноги Петра' not in page and 'name="owner"' not in page
    assert User.query.count() == 2
