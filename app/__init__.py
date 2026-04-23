from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from config import Config

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Пожалуйста, войдите для доступа к этой странице.'

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # Регистрация blueprints (пока заглушки)
    from app.routes import auth, main, exercises, templates, workouts
    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(exercises.bp)
    app.register_blueprint(templates.bp)
    app.register_blueprint(workouts.bp)

    return app