"""Вход, сессии, блокировка, сброс пароля (план 1.3, сброс пароля, 2.4)"""
from werkzeug.security import generate_password_hash

from app import db
from app.models import User, PasswordResetToken, load_user
from app.routes.auth import generate_reset_token
from conftest import login, csrf_token


def is_logged_in(client):
    return client.get('/dashboard').status_code == 200


def test_login_and_logout(client, make_user, csrf_app):
    make_user('anna')
    token = csrf_token(client)
    client.post('/auth/login', data={'username': 'anna', 'password': 'pass123', 'csrf_token': token})
    assert is_logged_in(client)
    assert client.get('/auth/logout').status_code == 405          # выход только POST
    client.post('/auth/logout', data={'csrf_token': csrf_token(client, '/dashboard')})
    assert not is_logged_in(client)


def test_wrong_password(client, make_user):
    make_user('anna')
    response = login(client, 'anna', 'wrong')
    assert 'Неверный логин' in response.get_data(as_text=True)
    assert not is_logged_in(client)


def test_password_change_ends_old_sessions(client, make_user):
    user = make_user('anna')
    login(client, 'anna')
    assert is_logged_in(client)
    user.password_hash = generate_password_hash('newpass')
    db.session.commit()
    assert not is_logged_in(client)


def test_blocked_user_is_logged_out_and_cannot_log_in(client, make_user):
    user = make_user('anna')
    login(client, 'anna')
    user.is_blocked = True
    db.session.commit()
    assert not is_logged_in(client)
    login(client, 'anna')
    assert not is_logged_in(client)


def test_load_user_rejects_old_format_and_forgery(make_user):
    user = make_user('anna')
    assert load_user(str(user.id)) is None
    assert load_user(f'{user.id}:forged') is None
    assert load_user(user.get_id()) is user


def test_forgot_password_does_not_reveal_email(client, make_user):
    make_user('anna')
    for email in ('anna@example.com', 'nobody@example.com'):
        page = client.post('/auth/forgot_password', data={'email': email}, follow_redirects=True).get_data(as_text=True)
        assert 'Если этот email зарегистрирован' in page


def test_reset_password_flow_invalidates_all_tokens(client, make_user):
    user = make_user('anna')
    first = generate_reset_token(user.id)
    second = generate_reset_token(user.id)
    client.post(f'/auth/reset_password/{second}', data={'password': 'newpass1', 'confirm_password': 'newpass1'})
    login(client, 'anna', 'newpass1')
    assert is_logged_in(client)
    assert PasswordResetToken.query.filter_by(user_id=user.id, used=False).count() == 0
    client.post('/auth/logout')
    page = client.get(f'/auth/reset_password/{first}', follow_redirects=True).get_data(as_text=True)
    assert 'недействительна' in page


def test_register_validates_email_and_shows_russian_errors(client):
    page = client.post('/auth/register', data={'username': 'ab', 'email': 'not-email',
                                               'password': '123', 'confirm_password': '321'}).get_data(as_text=True)
    for message in ('Имя — от 3 до 80 символов', 'Похоже, это не адрес почты', 'Пароль — не меньше 6 символов', 'Пароли не совпадают'):
        assert message in page
    assert User.query.count() == 0
