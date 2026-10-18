"""Общая подготовка для тестов.

Перед каждым тестом создаётся приложение с пустой базой в памяти (SQLite),
отключёнными CSRF и лимитами запросов. Запуск: `pytest` из корня проекта.
"""
import os
import re
from datetime import date, datetime, timedelta

# config.py читает переменные окружения при импорте — задаём их до импорта приложения
os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['ENVIRONMENT'] = 'development'
os.environ['SESSION_COOKIE_SECURE'] = 'False'
os.environ['SESSION_COOKIE_DOMAIN'] = ''

import pytest
from flask import g
from werkzeug.security import generate_password_hash

from app import create_app, db, limiter
from app.models import (Role, User, Exercise, WorkoutTemplate, TemplateExercise,
                        WorkoutSchedule, WorkoutSession, SetLog)

PASSWORD = 'pass123'


def _make_app(csrf=False):
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=csrf)
    limiter.enabled = False

    # Тест держит открытым контекст приложения, и запросы тестового клиента его переиспользуют.
    # Flask-Login (пользователь) и Flask-WTF (CSRF-токен) кэшируют данные в g этого контекста —
    # очищаем g перед каждым запросом, как будто это новый запрос на настоящем сервере.
    @app.before_request
    def _fresh_g():
        for key in list(vars(g)):
            delattr(g, key)

    return app


@pytest.fixture
def app():
    app = _make_app()
    with app.app_context():
        db.create_all()
        db.session.add_all([Role(id=1, name='admin', description=''),
                            Role(id=2, name='user', description=''),
                            Role(id=3, name='expert', description='')])
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def csrf_app(app):
    """То же приложение, но с включённой CSRF-защитой, как на сервере"""
    app.config['WTF_CSRF_ENABLED'] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


# ---------- фабрики данных ----------

@pytest.fixture
def make_user(app):
    def make(username='user', role_id=2, password=PASSWORD, **fields):
        user = User(username=username, email=f'{username}@example.com',
                    password_hash=generate_password_hash(password), role_id=role_id, **fields)
        db.session.add(user)
        db.session.commit()
        return user
    return make


@pytest.fixture
def make_exercise(app):
    def make(name, exercise_type='strength', author=None):
        exercise = Exercise(name=name, exercise_type=exercise_type,
                            created_by_id=author.id if author else 1)
        db.session.add(exercise)
        db.session.commit()
        return exercise
    return make


@pytest.fixture
def make_template(app):
    """Шаблон с упражнениями и расписанием на сегодня. exercises — список (exercise, plan)"""
    def make(owner, exercises, name='День ног', on=None):
        template = WorkoutTemplate(name=name, user_id=owner.id)
        db.session.add(template)
        db.session.commit()
        planned = {}
        for order, (exercise, plan) in enumerate(exercises):
            db.session.add(TemplateExercise(template_id=template.id, exercise_id=exercise.id, order=order))
            planned[str(exercise.id)] = plan
        schedule = WorkoutSchedule(user_id=owner.id, template_id=template.id,
                                   scheduled_date=on or date.today(), planned_data=planned)
        db.session.add(schedule)
        db.session.commit()
        return template, schedule
    return make


@pytest.fixture
def make_session(app):
    def make(owner, schedule=None, completed=False, days_ago=0, logs=()):
        """logs — список (exercise, reps, weight)"""
        session = WorkoutSession(user_id=owner.id,
                                 schedule_id=schedule.id if schedule else None,
                                 template_id=schedule.template_id if schedule else None,
                                 is_completed=completed, status='completed' if completed else 'in_progress',
                                 date=datetime.utcnow() - timedelta(days=days_ago))
        db.session.add(session)
        db.session.commit()
        for n, (exercise, reps, weight) in enumerate(logs, start=1):
            log = SetLog(session_id=session.id, exercise_id=exercise.id, set_number=n,
                         planned_reps=reps, planned_weight=weight, actual_reps=reps, actual_weight=weight)
            log.calculate_completion(80)
            db.session.add(log)
        db.session.commit()
        return session
    return make


def login(client, username, password=PASSWORD):
    return client.post('/auth/login', data={'username': username, 'password': password})


def csrf_token(client, url='/auth/login'):
    """CSRF-токен со страницы (для тестов с включённой защитой)"""
    html = client.get(url).get_data(as_text=True)
    return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)
