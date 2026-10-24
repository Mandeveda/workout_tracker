from flask import render_template, redirect, url_for, flash, request, Blueprint, session, current_app
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_, func
from datetime import datetime, timedelta
from flask_mail import Message
from urllib.parse import urlsplit
from markupsafe import escape
import secrets
from app import db, limiter, mail
from app.models import User, Role, PasswordResetToken
from app.forms import RegistrationForm, LoginForm, ForgotPasswordForm, ResetPasswordForm
from app import email_confirm
from app.timeutil import utcnow

bp = Blueprint('auth', __name__, url_prefix='/auth')

def is_safe_redirect(target):
    """Можно ли перейти по адресу после входа: только путь внутри сайта.

    Браузеры считают «\\» прямой косой чертой, поэтому «/\\evil.com» для них — это
    «//evil.com», то есть чужой сайт. Такие адреса, как и любые со схемой или доменом, отклоняем.
    """
    if not target:
        return False
    normalized = target.replace('\\', '/')
    parts = urlsplit(normalized)
    return normalized.startswith('/') and not normalized.startswith('//') and not parts.scheme and not parts.netloc


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
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Ошибка регистрации')
            flash('Ошибка при регистрации. Пожалуйста, попробуйте снова.', 'danger')
            return render_template('register.html', form=form)
        
        try:
            email_confirm.send_confirmation(user, user.email)
            flash(f'Аккаунт создан! Мы отправили письмо на {user.email} — перейдите по ссылке, чтобы подтвердить почту. '
                  f'Войти можно уже сейчас.', 'success')
        except Exception:
            current_app.logger.exception('Не удалось отправить письмо подтверждения (user_id=%s)', user.id)
            flash('Аккаунт создан! Письмо для подтверждения почты отправить не удалось — '
                  'войдите и отправьте его ещё раз из напоминания вверху страницы.', 'warning')
        return redirect(url_for('auth.login'))
    
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
        login_value = form.username.data.strip()
        user = User.query.filter(
            or_(
                User.username == login_value,
                func.lower(User.email) == login_value.lower()
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
            login_user(user, remember=True)
            
            # Возвращаем туда, откуда пришли, но только на страницу этого сайта
            next_page = request.args.get('next')
            return redirect(next_page if is_safe_redirect(next_page) else url_for('main.dashboard'))
        else:
            # Не показываем, существует ли пользователь или неверен пароль (безопасность)
            # От подбора пароля защищает лимит запросов на этот маршрут (5 в минуту)
            flash('Неверный логин/email или пароль', 'danger')
    
    return render_template('login.html', form=form)

@bp.route('/logout', methods=['POST'])
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
        user = User.query.filter(func.lower(User.email) == form.email.data).first()

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



@bp.route('/confirm_email/<token>')
def confirm_email(token):
    """Подтверждение почты по ссылке из письма (работает и без входа в аккаунт)"""
    data, problem = email_confirm.read_token(token)
    target = url_for('main.dashboard') if current_user.is_authenticated else url_for('auth.login')
    if problem == 'expired':
        flash('Ссылка устарела. Отправьте письмо ещё раз из напоминания вверху страницы.', 'warning')
        return redirect(target)
    user = db.session.get(User, data[0]) if data else None
    if not user:
        flash('Ссылка недействительна. Отправьте письмо ещё раз из напоминания вверху страницы.', 'danger')
        return redirect(target)
    
    email = (data[1] or '').lower()
    if user.pending_email and user.pending_email.lower() == email:
        taken = User.query.filter(func.lower(User.email) == email, User.id != user.id).first()
        if taken:
            flash('Этот адрес уже занят другим аккаунтом — укажите другую почту в профиле.', 'danger')
            return redirect(target)
        user.email = email
        user.pending_email = None
        user.email_confirmed_at = utcnow()
        db.session.commit()
        flash(f'Новая почта подтверждена: {email}', 'success')
    elif user.email.lower() == email:
        if not user.email_confirmed_at:
            user.email_confirmed_at = utcnow()
            db.session.commit()
        flash('Почта подтверждена. Спасибо!', 'success')
    else:
        flash('Ссылка устарела: адрес в аккаунте с тех пор изменился.', 'warning')
    return redirect(target)


@bp.route('/resend_confirmation', methods=['POST'])
@login_required
@limiter.limit("3 per hour")
def resend_confirmation():
    """Отправить письмо подтверждения ещё раз — на новый адрес, если идёт смена, иначе на текущий"""
    email = current_user.pending_email or (None if current_user.email_confirmed else current_user.email)
    back = request.form.get('next')
    back = back if is_safe_redirect(back) else url_for('main.dashboard')
    if not email:
        flash('Почта уже подтверждена.', 'info')
        return redirect(back)
    try:
        email_confirm.send_confirmation(current_user, email)
        flash(f'Письмо отправлено на {email}. Если его нет во «Входящих», проверьте «Спам».', 'success')
    except Exception:
        current_app.logger.exception('Не удалось отправить письмо подтверждения (user_id=%s)', current_user.id)
        flash('Не удалось отправить письмо. Попробуйте позже.', 'danger')
    return redirect(back)
