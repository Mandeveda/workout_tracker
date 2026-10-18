from flask import render_template, redirect, url_for, flash, request, Blueprint, session, current_app
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_
from datetime import datetime, timedelta
from flask_mail import Message
from markupsafe import escape
import secrets
from app import db, limiter, mail
from app.models import User, Role, PasswordResetToken
from app.forms import RegistrationForm, LoginForm, ForgotPasswordForm, ResetPasswordForm

bp = Blueprint('auth', __name__, url_prefix='/auth')

def regenerate_session():
    """Безопасная регенерация сессии для защиты от фиксации сессии"""
    # Сохраняем нужные данные из старой сессии
    old_session_data = dict(session)
    # Очищаем сессию
    session.clear()
    # Восстанавливаем необходимые данные
    for key, value in old_session_data.items():
        if key not in ['_fresh', 'csrf_token']:
            session[key] = value
    # Устанавливаем флаг свежей сессии
    session['_fresh'] = True
    session.permanent = True

@bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("3 per minute")
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        # Проверяем или создаём роль 'user'
        user_role = Role.query.filter_by(name='user').first()
        if not user_role:
            user_role = Role(name='user', description='Обычный пользователь')
            db.session.add(user_role)
            db.session.commit()
        
        # Создаём нового пользователя
        user = User(
            username=form.username.data,
            email=form.email.data,
            password_hash=generate_password_hash(form.password.data),
            role_id=user_role.id,
            is_blocked=False  # Явно указываем, что пользователь не заблокирован
        )
        
        try:
            db.session.add(user)
            db.session.commit()
            flash('Регистрация успешна! Теперь вы можете войти.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash('Ошибка при регистрации. Пожалуйста, попробуйте снова.', 'danger')
            return render_template('register.html', form=form)
    
    return render_template('register.html', form=form)

@bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    # Если пользователь уже авторизован, перенаправляем на дашборд
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        # Ищем пользователя по username или email
        user = User.query.filter(
            or_(
                User.username == form.username.data,
                User.email == form.username.data
            )
        ).first()
        
        # Проверяем пароль
        if user and check_password_hash(user.password_hash, form.password.data):
            
            # Проверяем, не заблокирован ли пользователь
            if user.is_blocked:
                flash('Ваш аккаунт заблокирован. Обратитесь к администратору.', 'danger')
                return redirect(url_for('auth.login'))
            
            # Регенерируем сессию для безопасности (защита от фиксации сессии)
            regenerate_session()
            
            # Выполняем вход
            login_user(user, remember=True)  # remember=True если нужно "запомнить меня"
            
            # Сохраняем дополнительную информацию в сессии
            session['user_id'] = user.id
            session['login_time'] = datetime.now().isoformat()
            session['user_username'] = user.username
            
            # Получаем следующий URL после входа
            next_page = request.args.get('next')
            
            # Проверяем безопасность next_url (защита от открытых редиректов)
            if next_page and not next_page.startswith(('http://', 'https://', '//')):
                if next_page.startswith('/'):
                    flash(f'Добро пожаловать, {user.username}!', 'success')
                    return redirect(next_page)
            
            # Если next_page не безопасен, редиректим на дашборд
            flash(f'Добро пожаловать, {user.username}!', 'success')
            return redirect(url_for('main.dashboard'))
        else:
            # Не показываем, существует ли пользователь или неверен пароль (безопасность)
            flash('Неверный логин/email или пароль', 'danger')
            # Небольшая задержка для защиты от брутфорса
            import time
            time.sleep(0.5)
    
    return render_template('login.html', form=form)

@bp.route('/logout')
@login_required
def logout():
    # Сохраняем имя пользователя для сообщения
    username = current_user.username
    
    # Очищаем сессию
    session.clear()
    
    # Выполняем выход
    logout_user()
    
    flash(f'Вы вышли из системы, {username}. До новых встреч!', 'info')
    return redirect(url_for('main.index'))

def generate_reset_token(user_id):
    """Генерация токена для сброса пароля"""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=24)
    
    reset_token = PasswordResetToken(
        user_id=user_id,
        token=token,
        expires_at=expires_at
    )
    db.session.add(reset_token)
    db.session.commit()
    
    return token

def send_reset_email(user, token):
    """Отправка письма со ссылкой для сброса пароля"""
    from flask import current_app
    
    sender = current_app.config.get('MAIL_DEFAULT_SENDER') or current_app.config.get('MAIL_USERNAME')
    
    if not sender:
        raise ValueError("MAIL_DEFAULT_SENDER не настроен в конфигурации")
    
    reset_url = url_for('auth.reset_password', token=token, _external=True,
                        _scheme=current_app.config.get('PREFERRED_URL_SCHEME', 'http'))
    username = escape(user.username)
    
    html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #007bff; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; background-color: #f8f9fa; }}
            .button {{ display: inline-block; background-color: #007bff; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; }}
            .footer {{ margin-top: 20px; font-size: 12px; color: #666; text-align: center; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>🔐 Workout Tracker</h2>
            </div>
            <div class="content">
                <h3>Здравствуйте, {username}!</h3>
                <p>Вы запросили сброс пароля. Нажмите на кнопку ниже, чтобы установить новый пароль:</p>
                <p style="text-align: center; margin: 30px 0;">
                    <a href="{reset_url}" class="button">Сбросить пароль</a>
                </p>
                <p>Ссылка действительна в течение 24 часов.</p>
                <p>Если вы не запрашивали сброс пароля, просто проигнорируйте это письмо.</p>
                <hr>
                <p style="font-size: 14px; color: #666;">
                    Или скопируйте ссылку в браузер:<br>
                    <code style="word-break: break-all;">{reset_url}</code>
                </p>
            </div>
            <div class="footer">
                <p>© 2026 Workout Tracker. Все права защищены.</p>
            </div>
        </div>
    </body>
    </html>
    '''
    
    msg = Message(
        subject='Сброс пароля — Workout Tracker',
        sender=sender,
        recipients=[user.email],
        html=html
    )
    
    mail.send(msg)

# Не чаще одного письма пользователю за этот интервал (защита ящика от спама с разных IP)
RESET_EMAIL_INTERVAL = timedelta(minutes=2)

@bp.route('/forgot_password', methods=['GET', 'POST'])
@limiter.limit("5 per hour", methods=['POST'])
def forgot_password():
    """Страница запроса сброса пароля"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    form = ForgotPasswordForm()

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()

        if user:
            recently_sent = PasswordResetToken.query.filter(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.created_at > datetime.utcnow() - RESET_EMAIL_INTERVAL
            ).first()

            if not recently_sent:
                # Действует только последняя ссылка: удаляем все прежние неиспользованные токены
                PasswordResetToken.query.filter_by(user_id=user.id, used=False).delete()
                db.session.commit()

                token = generate_reset_token(user.id)

                try:
                    send_reset_email(user, token)
                except Exception:
                    current_app.logger.exception('Ошибка отправки письма сброса пароля (user_id=%s)', user.id)
                    # Убираем токен, чтобы повторный запрос не попал под ограничение интервала
                    PasswordResetToken.query.filter_by(token=token).delete()
                    db.session.commit()
                    flash('Ошибка при отправке письма. Попробуйте позже.', 'danger')
                    return render_template('auth/forgot_password.html', form=form)

        # Одинаковый ответ независимо от того, существует ли email
        flash('Если этот email зарегистрирован, мы отправили на него ссылку для сброса пароля', 'info')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/forgot_password.html', form=form)

@bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Страница установки нового пароля по токену"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    reset_token = PasswordResetToken.query.filter_by(token=token, used=False).first()
    
    if not reset_token or reset_token.is_expired():
        flash('Ссылка для сброса пароля недействительна или истекла', 'danger')
        return redirect(url_for('auth.forgot_password'))
    
    form = ResetPasswordForm()
    
    if form.validate_on_submit():
        user = User.query.get(reset_token.user_id)
        user.password_hash = generate_password_hash(form.password.data)
        
        # Помечаем использованными все токены пользователя, а не только текущий
        PasswordResetToken.query.filter_by(user_id=user.id, used=False).update({'used': True})
        db.session.commit()
        
        flash('Пароль успешно изменён! Теперь вы можете войти с новым паролем.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/reset_password.html', form=form, token=token)
