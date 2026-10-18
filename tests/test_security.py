"""Этап 2 плана: безопасность"""
import pytest

from conftest import login


@pytest.mark.parametrize('target, expected', [
    ('/workouts/', '/workouts/'),
    ('/analytics/records?x=1', '/analytics/records?x=1'),
    ('/\\evil.com', '/dashboard'),           # браузер читает как //evil.com
    ('//evil.com', '/dashboard'),
    ('https://evil.com', '/dashboard'),
    ('http:evil.com', '/dashboard'),
    ('\\\\evil.com', '/dashboard'),
    ('workouts', '/dashboard'),              # относительный адрес без «/»
    ('/%5Cevil.com', '/%5Cevil.com'),        # закодированный «\» безопасен: браузер не раскодирует путь
])
def test_login_redirect_only_to_own_pages(client, make_user, target, expected):
    """План 2.3: открытый редирект через ?next="""
    make_user('anna')
    response = client.post('/auth/login?next=' + target.replace('%', '%25').replace('?', '%3F').replace('=', '%3D'),
                           data={'username': 'anna', 'password': 'pass123'})
    assert response.status_code == 302
    assert response.headers['Location'] == expected


def test_email_is_case_insensitive(client, make_user):
    """План 2.4: Anna@Example.com и anna@example.com — один адрес"""
    make_user('anna')                                           # anna@example.com
    page = client.post('/auth/register', data={'username': 'anna2', 'email': 'Anna@Example.COM',
                                               'password': '123456', 'confirm_password': '123456'}).get_data(as_text=True)
    assert 'Этот email уже зарегистрирован' in page

    response = login(client, 'ANNA@example.com')
    assert response.headers['Location'].endswith('/dashboard')


def test_new_email_stored_lowercase(client):
    from app.models import User
    client.post('/auth/register', data={'username': 'boris', 'email': '  Boris@Mail.RU ',
                                        'password': '123456', 'confirm_password': '123456'})
    assert User.query.filter_by(username='boris').one().email == 'boris@mail.ru'


def test_password_reset_finds_email_in_any_case(client, make_user, app):
    from app.models import PasswordResetToken
    from app import mail
    make_user('anna')
    app.config['MAIL_SUPPRESS_SEND'] = True
    with mail.record_messages() as outbox:
        client.post('/auth/forgot_password', data={'email': 'ANNA@Example.com'})
    assert len(outbox) == 1 and PasswordResetToken.query.count() == 1


SECRET_ERROR = 'sqlite3.OperationalError: /home/k/secret/workout.db is locked'


def _break_commit(monkeypatch):
    """Сохранение в базу падает с ошибкой, в тексте которой внутренние подробности"""
    from app import db
    def broken_commit():
        raise RuntimeError(SECRET_ERROR)
    monkeypatch.setattr(db.session, 'commit', broken_commit)


def test_profile_errors_do_not_leak_details(client, make_user, monkeypatch):
    """План 2.5: тексты исключений не показываются пользователю"""
    make_user('anna')
    login(client, 'anna')
    _break_commit(monkeypatch)
    page = client.post('/profile/add_measurement', data={'weight': '80'}, follow_redirects=True).get_data(as_text=True)
    assert SECRET_ERROR not in page and 'Не удалось сохранить' in page
    page = client.post('/profile/edit', data={'username': 'anna', 'weight': 81, 'height': 180, 'age': 30, 'gender': 'male',
                                              **{f'{k}_circumference': 0 for k in ('chest', 'waist', 'hips', 'biceps', 'forearm', 'thigh', 'calf', 'neck')}},
                       follow_redirects=True).get_data(as_text=True)
    assert SECRET_ERROR not in page and 'Не удалось сохранить' in page


def test_complete_workout_error_does_not_leak_details(client, make_user, make_exercise, make_template, make_session, monkeypatch):
    user = make_user('anna')
    _, schedule = make_template(user, [(make_exercise('Присед'), {'input_type': 'fixed', 'sets': 1, 'reps': 5, 'weight': 50})])
    session = make_session(user, schedule)
    login(client, 'anna')
    _break_commit(monkeypatch)
    response = client.post(f'/workouts/complete/{session.id}')
    assert response.status_code == 500
    assert SECRET_ERROR not in response.get_data(as_text=True)


def test_remember_cookie_settings(client, make_user, app):
    """План 2.6: cookie «запомнить меня» — 30 дней, только по HTTPS на сервере, недоступна JS"""
    from datetime import timedelta
    from config import ProductionConfig
    assert app.config['REMEMBER_COOKIE_DURATION'] == timedelta(days=30)
    assert ProductionConfig.REMEMBER_COOKIE_SECURE is True
    assert app.config['REMEMBER_COOKIE_HTTPONLY'] is True

    make_user('anna')
    response = login(client, 'anna')
    cookie = next(c for c in response.headers.getlist('Set-Cookie') if c.startswith('remember_token='))
    assert 'HttpOnly' in cookie and 'SameSite=Lax' in cookie


def test_app_does_not_enable_debug_logging(app):
    """План 2.7: модули не включают DEBUG-логирование для всего процесса (в лог писались замеры и подходы)"""
    import logging
    import app.routes.workouts, app.routes.profile  # noqa: F401 — импорт модулей не должен менять логирование
    assert logging.getLogger().level != logging.DEBUG
