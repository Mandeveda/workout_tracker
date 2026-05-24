import os
import sys

# Пути на Beget
HOME_DIR = '/home/ваш_логин'
SITE_DIR = f'{HOME_DIR}/ваш-домен.beget.tech'
VENV_DIR = f'{SITE_DIR}/venv'

# Добавляем пути
sys.path.insert(0, SITE_DIR)
sys.path.insert(0, f'{VENV_DIR}/lib/python3.11/site-packages')

# Устанавливаем переменные окружения
os.environ['ENVIRONMENT'] = 'production'

# Загружаем .env файл
from dotenv import load_dotenv
load_dotenv(f'{SITE_DIR}/.env')

# Создаём приложение
from app import create_app

application = create_app()

# Инициализация базы данных при первом запуске
with application.app_context():
    from app import db
    db.create_all()