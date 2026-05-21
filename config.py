import os
from dotenv import load_dotenv
from pathlib import Path
from datetime import timedelta  # ДОБАВИТЬ этот импорт

# Корень проекта (папка, где лежит config.py)
BASE_DIR = Path(__file__).resolve().parent

# Загружаем .env из корня
load_dotenv(BASE_DIR / '.env')

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Абсолютный путь к папке instance
    INSTANCE_PATH = BASE_DIR / 'instance'
    
    # Создаём папку instance принудительно
    INSTANCE_PATH.mkdir(exist_ok=True)
    
    # Путь к базе данных
    DB_PATH = INSTANCE_PATH / 'workout.db'
    
    # Используем абсолютный путь для SQLAlchemy
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{DB_PATH}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # ===== НАСТРОЙКИ БЕЗОПАСНОСТИ СЕССИИ =====
    # Основные настройки сессии
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False') == 'True'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_NAME = 'workout_session'  # ДОБАВИТЬ - имя cookie сессии
    SESSION_COOKIE_PATH = '/'  # ДОБАВИТЬ - путь для cookie
    SESSION_COOKIE_DOMAIN = None  # ДОБАВИТЬ - домен (None = текущий)
    
    # Время жизни сессии (в секундах) - ДОБАВИТЬ
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)  # 24 часа
    
    # Обновлять сессию при каждом запросе - ДОБАВИТЬ
    SESSION_REFRESH_EACH_REQUEST = True
    
    # ===== НАСТРОЙКИ CSRF ЗАЩИТЫ =====
    WTF_CSRF_ENABLED = True  # ДОБАВИТЬ - включаем CSRF защиту
    WTF_CSRF_TIME_LIMIT = 3600  # ДОБАВИТЬ - время жизни CSRF токена (1 час)
    WTF_CSRF_SECRET_KEY = os.environ.get('WTF_CSRF_SECRET_KEY', SECRET_KEY)  # ДОБАВИТЬ - ключ для CSRF
    
    # ===== НАСТРОЙКИ FLASK-LIMITER =====
    RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')
    RATELIMIT_STRATEGY = 'fixed-window'
    RATELIMIT_DEFAULT_LIMITS = ["200 per day", "50 per hour"]
    RATELIMIT_HEADERS_ENABLED = True  # ДОБАВИТЬ - показывать заголовки с лимитами
    
    # ===== ДОПОЛНИТЕЛЬНЫЕ НАСТРОЙКИ БЕЗОПАСНОСТИ =====
    # Защита от атак через Referer
    REFERRER_POLICY = 'same-origin'  # ДОБАВИТЬ
    
    # Максимальный размер загружаемых данных (в байтах)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB, ДОБАВИТЬ
    
    # Настройки для загрузки файлов (если используете)
    UPLOAD_FOLDER = BASE_DIR / 'uploads'
    UPLOAD_FOLDER.mkdir(exist_ok=True)
    
    @staticmethod
    def init_app(app):
        """Дополнительная инициализация приложения"""
        # Настройка заголовков безопасности
        @app.after_request
        def add_security_headers(response):
            # Защита от MIME-сниффинга
            response.headers['X-Content-Type-Options'] = 'nosniff'
            # Защита от кликджекинга
            response.headers['X-Frame-Options'] = 'DENY'
            # Защита от XSS (для старых браузеров)
            response.headers['X-XSS-Protection'] = '1; mode=block'
            # Referrer Policy
            response.headers['Referrer-Policy'] = Config.REFERRER_POLICY
            return response