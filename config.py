import os
from dotenv import load_dotenv
from pathlib import Path
from datetime import timedelta

# Корень проекта (папка, где лежит config.py)
BASE_DIR = Path(__file__).resolve().parent

# Загружаем .env из корня
load_dotenv(BASE_DIR / '.env')

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY не установлен в переменных окружения")

    # Абсолютный путь к папке instance (для SQLite, если не используем PostgreSQL)
    INSTANCE_PATH = BASE_DIR / 'instance'
    INSTANCE_PATH.mkdir(exist_ok=True)
    
    # ===== НАСТРОЙКИ БАЗЫ ДАННЫХ =====
    # Поддерживаем PostgreSQL для продакшена и SQLite для разработки
   # База данных
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        SQLALCHEMY_DATABASE_URI = database_url
    else:
        DB_PATH = INSTANCE_PATH / 'workout.db'
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{DB_PATH}'
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # ===== НАСТРОЙКИ БЕЗОПАСНОСТИ СЕССИИ =====
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_NAME = 'workout_session'
    SESSION_COOKIE_PATH = '/'
    SESSION_COOKIE_DOMAIN = os.environ.get('SESSION_COOKIE_DOMAIN', None)
    
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.environ.get('SESSION_LIFETIME_HOURS', 24)))
    SESSION_REFRESH_EACH_REQUEST = True
    
    # ===== НАСТРОЙКИ CSRF ЗАЩИТЫ =====
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 1800
    WTF_CSRF_SECRET_KEY = os.environ.get('WTF_CSRF_SECRET_KEY', SECRET_KEY)
    
    # ===== НАСТРОЙКИ FLASK-LIMITER =====
    # Поддерживаем Redis для продакшена
    REDIS_URL = os.environ.get('REDIS_URL')
    if REDIS_URL:
        RATELIMIT_STORAGE_URI = REDIS_URL
    else:
        RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')
    
    RATELIMIT_STRATEGY = 'fixed-window'
    RATELIMIT_DEFAULT_LIMITS = ["100 per day", "20 per hour"]
    RATELIMIT_HEADERS_ENABLED = True
    RATELIMIT_STORAGE_OPTIONS = {
        'socket_connect_timeout': 30,
        'socket_timeout': 30,
    } if REDIS_URL else {}
    
    # ===== ДОПОЛНИТЕЛЬНЫЕ НАСТРОЙКИ БЕЗОПАСНОСТИ =====
    REFERRER_POLICY = 'strict-origin-when-cross-origin'
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB
    
    UPLOAD_FOLDER = BASE_DIR / 'uploads'
    UPLOAD_FOLDER.mkdir(exist_ok=True)
    
    @staticmethod
    def init_app(app):
        """Дополнительная инициализация приложения"""
        @app.after_request
        def add_security_headers(response):
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'DENY'
            response.headers['X-XSS-Protection'] = '1; mode=block'
            response.headers['Referrer-Policy'] = Config.REFERRER_POLICY
            
            # Более мягкий CSP для разработки (можно усилить для продакшена)
            if os.environ.get('ENVIRONMENT') == 'production':
                response.headers['Content-Security-Policy'] = (
                    "default-src 'self' https://cdn.jsdelivr.net; "
                    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                    "font-src 'self' data: https://cdn.jsdelivr.net; "
                    "img-src 'self' data:; "
                    "connect-src 'self' https://cdn.jsdelivr.net;"
                )
            return response

# Настройки для разных окружений
class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    ENVIRONMENT = 'development'

class ProductionConfig(Config):
    DEBUG = False
    ENVIRONMENT = 'production'
    
    # Более строгие настройки для продакшена
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = 'Strict'

# Выбор конфигурации на основе переменной окружения
config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

def get_config():
    env = os.environ.get('ENVIRONMENT', 'development')
    return config_map.get(env, DevelopmentConfig)