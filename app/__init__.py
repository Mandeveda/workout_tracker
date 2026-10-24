from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config import get_config
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail
import os

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Пожалуйста, войдите для доступа к этой странице.'

limiter = Limiter(key_func=get_remote_address)
csrf = CSRFProtect()  # Создаем экземпляр здесь

mail = Mail()

def create_app(config_class=None):
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
    # render_as_batch: SQLite не умеет большинство ALTER TABLE — Alembic пересоздаёт таблицу
    migrate.init_app(app, db, render_as_batch=True)
    login_manager.init_app(app)
    mail.init_app(app)
    
    # Инициализация CSRF - ВАЖНО: используем init_app, а не создаем новый экземпляр
    csrf.init_app(app)
    
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
    
    # Контекстный процессор для CSRF токена (ВАЖНО!)
    @app.context_processor
    def inject_csrf_token():
        """Добавляет CSRF токен в шаблоны"""
        from flask_wtf.csrf import generate_csrf
        return dict(csrf_token=generate_csrf)
    
    # nonce для встроенных скриптов: <script nonce="{{ csp_nonce() }}">
    @app.context_processor
    def inject_csp_nonce():
        from app.security import csp_nonce
        return dict(csp_nonce=csp_nonce)
    
    # Контекстный процессор для current_user
    @app.context_processor
    def inject_user():
        from flask_login import current_user
        return dict(current_user=current_user)
    
    @app.template_filter('num')
    def format_number(value, digits=0):
        """Число с разделителем разрядов: 12345.6 → «12 346», с digits=1 → «12 345,6»"""
        try:
            text = f'{float(value):,.{digits}f}'
        except (TypeError, ValueError):
            return value
        return text.replace(',', '\u00a0').replace('.', ',')
    
    @app.template_filter('local')
    def local_time(value):
        """UTC из базы → местное время сайта: {{ session.date|local|strftime... }}"""
        from app.timeutil import to_local
        return to_local(value)
    
    from app.textutil import plural
    app.add_template_filter(plural, 'plural')   # {{ n|plural('упражнение', 'упражнения', 'упражнений') }}
    
    # Версия у ссылок на статику (?v=время изменения файла): после обновления файла
    # браузер и service worker сразу берут новую версию, а не старую из кэша
    static_versions = {}

    @app.url_defaults
    def static_file_version(endpoint, values):
        if endpoint == 'static' and 'filename' in values:
            filename = values['filename']
            if filename not in static_versions:
                try:
                    static_versions[filename] = int(os.path.getmtime(os.path.join(app.static_folder, filename)))
                except OSError:
                    static_versions[filename] = 0
            values.setdefault('v', static_versions[filename])
    
    # Технические работы (переезд базы и т. п.): пока есть файл instance/maintenance,
    # любой запрос получает 503 и ничего не пишется в базу. Включить: touch instance/maintenance
    app.config.setdefault('MAINTENANCE_FILE', os.path.join(app.config.get('INSTANCE_PATH') or app.instance_path, 'maintenance'))

    @app.before_request
    def maintenance_mode():
        from flask import request, render_template
        if request.endpoint != 'static' and os.path.exists(app.config['MAINTENANCE_FILE']):
            return render_template('maintenance.html'), 503, {'Retry-After': '600', 'Cache-Control': 'no-store'}

    # «Был на сайте» для админки: пишем в базу не чаще раза в 5 минут, а не на каждый запрос
    # (после ответа: пользователь к этому моменту уже загружен, а изменения страницы сохранены)
    @app.after_request
    def remember_last_seen(response):
        from flask import request
        from flask_login import current_user
        from app.models import User, LAST_SEEN_STEP
        from app.timeutil import utcnow
        if (response.status_code == 503 or request.endpoint in (None, 'static', 'main.service_worker')
                or not current_user.is_authenticated):
            return response   # 503 — технические работы: базу не трогаем
        now = utcnow()
        if current_user.last_seen_at and now - current_user.last_seen_at < LAST_SEEN_STEP:
            return response
        try:
            db.session.execute(db.update(User).where(User.id == current_user.id).values(last_seen_at=now))
            db.session.commit()
        except Exception:
            db.session.rollback()   # отметка не важнее самого запроса
        return response
    
    # Обработчик ошибки превышения лимита
    @app.errorhandler(429)
    def ratelimit_handler(e):
        return {'error': 'Too many requests. Please try again later.'}, 429
    
    return app