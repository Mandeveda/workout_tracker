"""План 5.1: миграции создают с нуля ту же схему, что описывают модели"""
import os
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(__file__), '..')


def flask_db(command, db_path):
    env = {**os.environ, 'DATABASE_URL': f'sqlite:///{db_path}', 'ENVIRONMENT': 'development'}
    return subprocess.run([sys.executable, '-m', 'flask', '--app', 'run', 'db', command],
                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)


def test_migrations_build_schema_matching_models(tmp_path):
    db_path = tmp_path / 'fresh.db'
    upgrade = flask_db('upgrade', db_path)
    assert upgrade.returncode == 0, upgrade.stderr
    check = flask_db('check', db_path)                 # падает, если модели и миграции расходятся
    assert check.returncode == 0, check.stderr + check.stdout
    assert 'No new upgrade operations detected' in check.stdout + check.stderr
