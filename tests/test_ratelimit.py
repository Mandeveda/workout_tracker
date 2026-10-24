"""План 5.3: счётчики лимитов в Redis — общие для всех процессов сервера"""
import os
import socket
import subprocess
import sys
import time

import pytest

from config import redis_storage_uri

ROOT = os.path.join(os.path.dirname(__file__), '..')

# Отдельный процесс = отдельный процесс Passenger: своё приложение, своя память
WORKER = r'''
import os, sys
from app import create_app, db
from app.models import Role, User
from werkzeug.security import generate_password_hash
app = create_app(); app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
with app.app_context():
    db.create_all(); db.session.add(Role(id=2, name='user', description=''))
    db.session.add(User(username='anna', email='a@x.ru', password_hash=generate_password_hash('pass123'))); db.session.commit()
    c = app.test_client()
    print(' '.join(str(c.post('/auth/login', data={'username': 'anna', 'password': 'wrong'}).status_code)
                   for _ in range(int(sys.argv[1]))))
'''


@pytest.mark.parametrize('raw, expected', [
    ('redis://localhost:6379/0', 'redis://localhost:6379/0'),
    ('redis://:secret@127.0.0.1:6379/1', 'redis://:secret@127.0.0.1:6379/1'),
    ('unix:///home/k/user/.redis/redis.sock', 'redis+unix:///home/k/user/.redis/redis.sock'),
    ('/home/k/user/.redis/redis.sock', 'redis+unix:///home/k/user/.redis/redis.sock'),
    (' redis+unix:///run/redis.sock ', 'redis+unix:///run/redis.sock'),
])
def test_redis_storage_uri(raw, expected):
    assert redis_storage_uri(raw) == expected


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def run_worker(redis_url, attempts):
    env = {**os.environ, 'REDIS_URL': redis_url, 'DATABASE_URL': 'sqlite://', 'ENVIRONMENT': 'development'}
    result = subprocess.run([sys.executable, '-c', WORKER, str(attempts)], cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return result.stdout.split()


@pytest.fixture
def redis_server(tmp_path):
    """Настоящий redis-server (из пакета redislite, requirements-dev.txt) на порту и сокет-файле"""
    redislite = pytest.importorskip('redislite')
    port, sock = free_port(), tmp_path / 'redis.sock'
    proc = subprocess.Popen([redislite.__redis_executable__, '--port', str(port), '--unixsocket', str(sock),
                             '--save', '', '--appendonly', 'no'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        if sock.exists():
            break
        time.sleep(0.1)
    yield {'tcp': f'redis://127.0.0.1:{port}/0', 'socket': str(sock)}
    proc.terminate()
    proc.wait(timeout=10)


@pytest.mark.parametrize('kind', ['tcp', 'socket'])
def test_two_processes_share_login_limit(redis_server, kind):
    """5 попыток в минуту: 3 в одном процессе + 3 в другом — шестая отклоняется (429).
    'socket' — путь к сокет-файлу, как Redis обычно подключён на хостинге"""
    url = redis_server[kind]
    assert run_worker(url, 3) == ['200', '200', '200']
    assert run_worker(url, 3) == ['200', '200', '429']


def test_site_works_when_redis_is_down():
    """Redis недоступен — вход не падает с 500, лимиты временно считаются в памяти"""
    statuses = run_worker(f'redis://127.0.0.1:{free_port()}/0', 6)
    assert '500' not in statuses
    assert statuses[:5] == ['200'] * 5 and statuses[5] == '429'
