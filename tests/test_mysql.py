"""ROADMAP C: подготовка к MySQL — настройки подключения, схема, перенос данных, техработы"""
import os
import sqlite3
import subprocess
import sys

from config import database_settings
from app import db
from app.models import WorkoutTemplate
from tests.conftest import PASSWORD, login
from tests.test_migrations import ROOT, flask_db


def test_mysql_url_gets_driver_charset_and_pool_settings():
    url, options = database_settings('mysql://u:p@localhost/tw')
    assert url == 'mysql+pymysql://u:p@localhost/tw?charset=utf8mb4'
    assert options['pool_pre_ping'] and options['pool_recycle'] < 3600
    assert database_settings('mysql+pymysql://u:p@localhost/tw?charset=utf8mb4')[0].count('charset') == 1
    assert database_settings('sqlite:///x.db') == ('sqlite:///x.db', {})


def test_migrations_render_valid_mysql_schema():
    """Миграции в режиме «показать SQL» для MySQL: utf8mb4, DOUBLE вместо 4-байтного FLOAT"""
    env = {**os.environ, 'DATABASE_URL': 'mysql://u:p@localhost/tw', 'ENVIRONMENT': 'development'}
    result = subprocess.run([sys.executable, '-m', 'flask', '--app', 'run', 'db', 'upgrade', '--sql'],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    sql = result.stdout
    assert 'ALTER DATABASE CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci' in sql
    assert 'FLOAT' not in sql and sql.count('DOUBLE') == 17
    assert 'password_hash VARCHAR(256)' in sql or 'MODIFY password_hash VARCHAR(256)' in sql


def transfer(*args):
    return subprocess.run([sys.executable, 'transfer_to_mysql.py', *args], cwd=ROOT,
                          capture_output=True, text=True, timeout=120)


def test_transfer_copies_everything_and_rehearsal_rolls_back(tmp_path):
    source, target = tmp_path / 'src.db', tmp_path / 'dst.db'
    for path in (source, target):
        assert flask_db('upgrade', path).returncode == 0
    with sqlite3.connect(source) as con:
        con.execute("INSERT INTO roles (id, name) VALUES (2, 'user')")
        con.execute("INSERT INTO users (id, username, email, role_id, password_hash, weight, measurements_history, created_at) "
                    "VALUES (7, 'Алёна', 'a@example.com', 2, ?, 61.7, '[{\"weight\": 61.7}]', '2026-05-01 10:00:00.123456')",
                    ('scrypt:' + 'x' * 155,))
        con.execute("INSERT INTO workout_templates (id, name, user_id, is_active) VALUES (3, 'Спина 💪', 7, 1)")
    args = ['--from', f'sqlite:///{source}', '--to', f'sqlite:///{target}']

    rehearsal = transfer(*args)
    assert rehearsal.returncode == 0, rehearsal.stdout + rehearsal.stderr
    assert 'Репетиция прошла' in rehearsal.stdout
    with sqlite3.connect(target) as con:
        assert con.execute('SELECT COUNT(*) FROM users').fetchone() == (0,)

    applied = transfer(*args, '--apply')
    assert applied.returncode == 0, applied.stdout + applied.stderr
    with sqlite3.connect(target) as con:
        assert con.execute('SELECT id, username, weight FROM users').fetchall() == [(7, 'Алёна', 61.7)]
        assert con.execute('SELECT name FROM workout_templates').fetchall() == [('Спина 💪',)]

    again = transfer(*args, '--apply')                      # в заполненную базу — отказ
    assert again.returncode == 1 and 'уже есть данные' in again.stdout


def test_transfer_refuses_data_mysql_would_reject(tmp_path):
    source, target = tmp_path / 'src.db', tmp_path / 'dst.db'
    for path in (source, target):
        assert flask_db('upgrade', path).returncode == 0
    with sqlite3.connect(source) as con:                    # SQLite не проверяет ссылки и длину
        con.execute("INSERT INTO workout_templates (id, name, user_id) VALUES (1, ?, 99)", ('Ж' * 150,))
    result = transfer('--from', f'sqlite:///{source}', '--to', f'sqlite:///{target}', '--apply')
    assert result.returncode == 1
    assert 'workout_templates.user_id: 1 строк ссылаются на несуществующие users' in result.stdout
    assert 'workout_templates.name: 1 строк длиннее 100 символов' in result.stdout


def test_transfer_refuses_different_revisions(tmp_path):
    source, target = tmp_path / 'src.db', tmp_path / 'dst.db'
    assert flask_db('upgrade', source).returncode == 0
    assert flask_db('upgrade', target, 'acd378e663a7').returncode == 0
    result = transfer('--from', f'sqlite:///{source}', '--to', f'sqlite:///{target}')
    assert result.returncode == 1 and 'ревизии миграций не совпадают' in result.stdout


def test_maintenance_mode_closes_site(app, client, make_user, tmp_path):
    make_user('ivan')
    login(client, 'ivan')
    flag = tmp_path / 'maintenance'
    app.config['MAINTENANCE_FILE'] = str(flag)
    flag.touch()
    response = client.get('/dashboard')
    assert response.status_code == 503 and 'Технические работы' in response.get_data(as_text=True)
    assert client.post('/auth/login', data={'username': 'ivan', 'password': PASSWORD}).status_code == 503
    flag.unlink()
    assert client.get('/dashboard').status_code == 200


def test_lengths_mysql_would_reject_are_validated(client, make_user):
    user = make_user('ivan')
    long_email = 'a' * 115 + '@mail.ru'
    page = client.post('/auth/register', data={'username': 'newbie', 'email': long_email, 'password': PASSWORD,
                                               'confirm_password': PASSWORD}).get_data(as_text=True)
    assert 'не длиннее 120 символов' in page
    template = WorkoutTemplate(name='Спина', user_id=user.id)
    db.session.add(template)
    db.session.commit()
    login(client, 'ivan')
    client.post(f'/templates/edit/{template.id}', data={'edit_name': '1', 'name': 'Ж' * 101})
    db.session.refresh(template)
    assert template.name == 'Спина'
