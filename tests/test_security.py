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
