from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config import get_config, Config
import os

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Пожалуйста, войдите для доступа к этой странице.'

limiter = Limiter(key_func=get_remote_address)

def create_app(config_class=Config):
    if config_class is None:
        config_class = get_config()
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Вызываем дополнительную инициализацию из config
    config_class.init_app(app)
    
    # Убеждаемся, что папка instance существует
    os.makedirs(app.config['INSTANCE_PATH'], exist_ok=True)
    
    # Инициализация расширений
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    
    # Инициализация limiter
    limiter.init_app(app)
    
    # Регистрация blueprints
    from app.routes import auth, main, exercises, templates, program, workouts, analytics, admin, profile
    
    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(exercises.bp)
    app.register_blueprint(templates.bp)
    app.register_blueprint(workouts.bp)
    app.register_blueprint(program.bp)
    app.register_blueprint(analytics.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(profile.bp)
    
    # Контекстный процессор для current_user
    @app.context_processor
    def inject_user():
        from flask_login import current_user
        return dict(current_user=current_user)
    
    # Обработчик ошибки превышения лимита
    @app.errorhandler(429)
    def ratelimit_handler(e):
        return {'error': 'Too many requests. Please try again later.'}, 429
    
    return app