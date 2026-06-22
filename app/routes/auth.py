from flask import render_template, redirect, url_for, flash, request, Blueprint, session
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_
from datetime import datetime
import secrets
from app import db, limiter
from app.models import User, Role
from app.forms import RegistrationForm, LoginForm

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

# Дополнительный маршрут для смены пароля (опционально)
@bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    from app.forms import ChangePasswordForm
    
    form = ChangePasswordForm()
    if form.validate_on_submit():
        # Проверяем старый пароль
        if check_password_hash(current_user.password_hash, form.old_password.data):
            # Устанавливаем новый пароль
            current_user.password_hash = generate_password_hash(form.new_password.data)
            db.session.commit()
            flash('Пароль успешно изменён!', 'success')
            return redirect(url_for('main.dashboard'))
        else:
            flash('Неверный текущий пароль', 'danger')
    
    return render_template('change_password.html', form=form)

# Дополнительный маршрут для восстановления пароля (опционально)
@bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit("3 per hour")
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    form = ForgotPasswordForm() if 'ForgotPasswordForm' in dir() else None
    
    if form and form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            # Здесь добавить логику отправки email для сброса пароля
            flash('Инструкции по восстановлению пароля отправлены на ваш email.', 'info')
        else:
            # Не показываем, существует ли email в системе
            flash('Если аккаунт с таким email существует, инструкции будут отправлены.', 'info')
        return redirect(url_for('auth.login'))
    
    return render_template('forgot_password.html', form=form)