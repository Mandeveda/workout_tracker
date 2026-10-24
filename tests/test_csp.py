"""План 5.4: CSP без 'unsafe-inline' для скриптов — встроенные скрипты помечены nonce"""
import glob
import os
import re

import pytest

from conftest import login

TEMPLATES = os.path.join(os.path.dirname(__file__), '..', 'app', 'templates')


def policy(response):
    return dict(part.strip().split(' ', 1) for part in response.headers['Content-Security-Policy'].split(';') if part.strip())


def test_csp_header(client):
    csp = policy(client.get('/auth/login'))
    assert "'unsafe-inline'" not in csp['script-src'] and "'nonce-" in csp['script-src']
    assert 'https://www.youtube.com' in csp['frame-src']                 # видео в «Технике выполнения»
    assert 'https://fonts.gstatic.com' in csp['connect-src']             # service worker кэширует шрифты
    assert csp['object-src'] == "'none'" and csp['frame-ancestors'] == "'none'"


def test_nonce_changes_every_request(client):
    first = policy(client.get('/auth/login'))['script-src']
    second = policy(client.get('/auth/login'))['script-src']
    assert first != second


def test_no_inline_event_handlers_in_templates():
    """onclick= и подобные с nonce не работают — только addEventListener"""
    offenders = []
    for path in glob.glob(os.path.join(TEMPLATES, '**', '*.html'), recursive=True):
        with open(path, encoding='utf-8') as f:
            for n, line in enumerate(f, 1):
                if re.search(r'\son[a-z]+="', line):
                    offenders.append(f'{os.path.relpath(path, TEMPLATES)}:{n}')
    assert offenders == []


@pytest.fixture
def pages(make_user, make_exercise, make_template, make_session):
    user = make_user('anna', role_id=1)
    squat = make_exercise('Присед')
    template, schedule = make_template(user, [(squat, {'input_type': 'fixed', 'sets': 3, 'reps': 8, 'weight': 60})])
    session = make_session(user, schedule)
    done = make_session(user, completed=True, logs=[(squat, 8, 60)])
    return ['/', '/dashboard', '/workouts/', '/workouts/free_workout', f'/workouts/perform/{session.id}',
            f'/workouts/summary/{done.id}', '/templates/', f'/templates/edit/{template.id}',
            f'/templates/add_exercise/{template.id}', f'/program/create/{template.id}', '/exercises/',
            '/exercises/add', '/analytics/dashboard', '/analytics/records', '/analytics/progress',
            '/analytics/calendar', '/profile/', '/profile/edit', '/admin/users', '/offline']


def test_every_inline_script_has_request_nonce(client, pages):
    login(client, 'anna')
    for url in pages:
        response = client.get(url)
        assert response.status_code == 200, url
        nonce = re.search(r"'nonce-([^']+)'", response.headers['Content-Security-Policy']).group(1)
        html = response.get_data(as_text=True)
        for tag in re.findall(r'<script\b[^>]*>', html):
            if 'src=' in tag or 'application/json' in tag:
                continue
            assert f'nonce="{nonce}"' in tag, f'{url}: {tag}'
