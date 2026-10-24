import sys
import os
import logging

# Путь к виртуальному окружению
SITE_DIR = '/home/k/kandybd9/tracker-workout.ru'
VENV_DIR = f'{SITE_DIR}/venv_tw'

sys.path.insert(0, SITE_DIR)
sys.path.insert(0, f'{VENV_DIR}/lib/python3.10/site-packages')

# База — DATABASE_URL в .env (MySQL); если не задан — SQLite в instance/workout.db

logging.basicConfig(stream=sys.stderr, level=logging.WARNING)

from app import create_app
application = create_app()