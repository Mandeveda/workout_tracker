"""Профиль: смена пароля (план 5.5)"""
from conftest import login


def form(old, new, confirm=None):
    return {'old_password': old, 'new_password': new, 'confirm_password': confirm or new}


def test_change_password(client, app, make_user):
    make_user('anna')
    login(client, 'anna')
    other_device = app.test_client()
    login(other_device, 'anna')

    page = client.post('/profile/change_password', data=form('pass123', 'newpass1'), follow_redirects=True).get_data(as_text=True)
    assert 'Пароль изменён' in page
    assert client.get('/dashboard').status_code == 200          # текущее устройство остаётся в системе
    assert other_device.get('/dashboard').status_code == 302    # остальные входы завершены

    fresh = app.test_client()
    assert login(fresh, 'anna', 'newpass1').headers['Location'].endswith('/dashboard')


def test_change_password_requires_current_password(client, make_user):
    make_user('anna')
    login(client, 'anna')
    page = client.post('/profile/change_password', data=form('wrong', 'newpass1'), follow_redirects=True).get_data(as_text=True)
    assert 'Текущий пароль указан неверно' in page
    client.post('/auth/logout')
    assert login(client, 'anna', 'pass123').headers['Location'].endswith('/dashboard')


def test_change_password_validation(client, make_user):
    make_user('anna')
    login(client, 'anna')
    page = client.post('/profile/change_password', data=form('pass123', '123', '321'), follow_redirects=True).get_data(as_text=True)
    assert 'не менее 6 символов' in page or 'Пароли должны совпадать' in page
    assert client.get('/profile/change_password').status_code == 405
