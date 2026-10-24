"""План 5.1: миграции создают с нуля ту же схему, что описывают модели"""
import os
import sqlite3
from datetime import datetime, timedelta
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(__file__), '..')


def flask_db(command, db_path, *args):
    env = {**os.environ, 'DATABASE_URL': f'sqlite:///{db_path}', 'ENVIRONMENT': 'development'}
    return subprocess.run([sys.executable, '-m', 'flask', '--app', 'run', 'db', command, *args],
                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)


def test_migrations_build_schema_matching_models(tmp_path):
    db_path = tmp_path / 'fresh.db'
    upgrade = flask_db('upgrade', db_path)
    assert upgrade.returncode == 0, upgrade.stderr
    check = flask_db('check', db_path)                 # падает, если модели и миграции расходятся
    assert check.returncode == 0, check.stderr + check.stdout
    assert 'No new upgrade operations detected' in check.stdout + check.stderr


def test_email_migration_gives_existing_users_30_days(tmp_path):
    """ROADMAP A.1: уже зарегистрированным срок подтверждения отсчитывается от обновления"""
    db_path = tmp_path / 'old.db'
    assert flask_db('upgrade', db_path, 'b7e2a9c41d03').returncode == 0
    with sqlite3.connect(db_path) as con:
        con.execute("INSERT INTO roles (id, name) VALUES (2, 'user')")
        con.execute("INSERT INTO users (username, email, role_id, created_at) "
                    "VALUES ('old', 'old@example.com', 2, '2025-01-01 00:00:00')")
    upgrade = flask_db('upgrade', db_path)
    assert upgrade.returncode == 0, upgrade.stderr
    with sqlite3.connect(db_path) as con:
        confirmed, deadline = con.execute(
            "SELECT email_confirmed_at, email_confirm_deadline FROM users").fetchone()
    assert confirmed is None
    left = datetime.fromisoformat(deadline) - datetime.utcnow()
    assert timedelta(days=29) < left <= timedelta(days=30)


def test_template_history_migration_saves_template_names(tmp_path):
    """ROADMAP B: у проведённых тренировок сохраняется название шаблона"""
    db_path = tmp_path / 'old.db'
    assert flask_db('upgrade', db_path, 'c3d8e1f04a27').returncode == 0
    with sqlite3.connect(db_path) as con:
        con.execute("INSERT INTO roles (id, name) VALUES (2, 'user')")
        con.execute("INSERT INTO users (id, username, email, role_id) VALUES (1, 'u', 'u@example.com', 2)")
        con.execute("INSERT INTO workout_templates (id, name, user_id) VALUES (1, 'Спина', 1)")
        con.execute("INSERT INTO workout_sessions (user_id, template_id, date) VALUES (1, 1, '2026-01-01')")
        con.execute("INSERT INTO workout_sessions (user_id, template_id, date) VALUES (1, NULL, '2026-01-02')")
    upgrade = flask_db('upgrade', db_path)
    assert upgrade.returncode == 0, upgrade.stderr
    with sqlite3.connect(db_path) as con:
        names = [row[0] for row in con.execute("SELECT template_name FROM workout_sessions ORDER BY id")]
    assert names == ['Спина', None]
