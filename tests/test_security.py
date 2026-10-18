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
