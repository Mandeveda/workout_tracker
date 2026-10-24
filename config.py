import os
from dotenv import load_dotenv
from pathlib import Path
from datetime import timedelta

# Корень проекта (папка, где лежит config.py)
BASE_DIR = Path(__file__).resolve().parent

# Загружаем .env из корня
load_dotenv(BASE_DIR / '.env')


def env_bool(name, default):
    """Читает булеву переменную окружения ('True'/'False', '1'/'0', 'yes'/'no')"""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ('true', '1', 'yes', 'on')

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
    SESSION_COOKIE_SECURE = env_bool('SESSION_COOKIE_SECURE', True)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_NAME = 'workout_session'
    SESSION_COOKIE_PATH = '/'
    SESSION_COOKIE_DOMAIN = os.environ.get('SESSION_COOKIE_DOMAIN', None)
    
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.environ.get('SESSION_LIFETIME_HOURS', 24)))

    # Часовой пояс сайта: от него зависят «сегодня», неделя и календарь (в базе время в UTC)
    APP_TIMEZONE = os.environ.get('APP_TIMEZONE', 'Europe/Moscow')

    # Cookie «запомнить меня» (Flask-Login): по умолчанию она живёт год и без флага Secure
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE      # только по HTTPS там, где HTTPS
    REMEMBER_COOKIE_HTTPONLY = True                     # недоступна JavaScript
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    SESSION_REFRESH_EACH_REQUEST = True
    
    # ===== НАСТРОЙКИ CSRF ЗАЩИТЫ =====
    WTF_CSRF_ENABLED = True
    # Без ограничения по времени: токен и так привязан к сессии, а тренировка длится дольше 30 минут
    WTF_CSRF_TIME_LIMIT = None
    WTF_CSRF_SECRET_KEY = os.environ.get('WTF_CSRF_SECRET_KEY', SECRET_KEY)
    
    # ===== НАСТРОЙКИ FLASK-LIMITER =====
    # Поддерживаем Redis для продакшена
    REDIS_URL = os.environ.get('REDIS_URL')
    if REDIS_URL:
        RATELIMIT_STORAGE_URI = REDIS_URL
    else:
        RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')
    
    RATELIMIT_STRATEGY = 'fixed-window'
    RATELIMIT_HEADERS_ENABLED = True
    RATELIMIT_STORAGE_OPTIONS = {
        'socket_connect_timeout': 30,
        'socket_timeout': 30,
    } if REDIS_URL else {}
    
    # ===== НАСТРОЙКИ EMAIL =====
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.yandex.ru')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 465))
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'True') == 'True'
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'False') == 'True'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', MAIL_USERNAME)

    # Принудительно устанавливаем, если не задан
    if not MAIL_DEFAULT_SENDER and MAIL_USERNAME:
        MAIL_DEFAULT_SENDER = MAIL_USERNAME
    
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
            response.headers['Referrer-Policy'] = Config.REFERRER_POLICY
            
            # CSP: скрипты — только свои, с CDN и встроенные с nonce этого запроса
            # (внедрённый в страницу чужой скрипт nonce не знает и не выполнится).
            # Стили допускают 'unsafe-inline' — нужны атрибуты style (ширина полос и т. п.).
            from app.security import csp_nonce
            cdn = 'https://cdn.jsdelivr.net'
            fonts = 'https://fonts.googleapis.com https://fonts.gstatic.com'
            response.headers['Content-Security-Policy'] = '; '.join([
                "default-src 'self'",
                f"script-src 'self' 'nonce-{csp_nonce()}' {cdn}",
                f"style-src 'self' 'unsafe-inline' {cdn} https://fonts.googleapis.com",
                f"font-src 'self' data: {cdn} https://fonts.gstatic.com",
                "img-src 'self' data: https:",
                f"connect-src 'self' {cdn} {fonts}",      # service worker кэширует CDN и шрифты
                "frame-src https://www.youtube.com https://www.youtube-nocookie.com",   # видео техники
                "worker-src 'self'",
                "manifest-src 'self'",
                "object-src 'none'",
                "base-uri 'self'",
                "form-action 'self'",
                "frame-ancestors 'none'",
            ])
            return response

# Настройки для разных окружений
class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = env_bool('SESSION_COOKIE_SECURE', False)
    ENVIRONMENT = 'development'
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE

class ProductionConfig(Config):
    DEBUG = False
    ENVIRONMENT = 'production'
    
    # Более строгие настройки для продакшена
    SESSION_COOKIE_SAMESITE = 'Strict'
    REMEMBER_COOKIE_SECURE = True
    # Схема для внешних ссылок (письма): за Passenger запрос может прийти как http
    PREFERRED_URL_SCHEME = 'https'

# Выбор конфигурации на основе переменной окружения
config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

def get_config():
    env = os.environ.get('ENVIRONMENT', 'development')
    return config_map.get(env, DevelopmentConfig)