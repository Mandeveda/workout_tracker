from flask import render_template, redirect, url_for, flash, request, Blueprint
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from app import db
from app.models import User, Role
from sqlalchemy import or_

bp = Blueprint('admin', __name__, url_prefix='/admin')

def is_admin():
    """Проверка, является ли пользователь администратором"""
    return current_user.is_authenticated and current_user.role.name == 'admin'

@bp.route('/users')
@login_required
def users():
    """Управление пользователями (только для админов)"""
    if not is_admin():
        flash('Доступ запрещён. Требуются права администратора.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    # Поиск пользователей
    search = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    query = User.query
    
    if search:
        query = query.filter(
            or_(
                User.username.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%')
            )
        )
    
    users = query.order_by(User.id).paginate(page=page, per_page=per_page, error_out=False)
    roles = Role.query.all()
    
    return render_template('admin/users.html', users=users, roles=roles, search=search)

@bp.route('/user/<int:user_id>/role', methods=['POST'])
@login_required
def change_role(user_id):
    """Изменение роли пользователя"""
    if not is_admin():
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('main.dashboard'))
    
    user = User.query.get_or_404(user_id)
    
    # Нельзя менять роль супер-админа
    if user.id == current_user.id:
        flash('Нельзя изменить свою собственную роль', 'warning')
        return redirect(url_for('admin.users'))
    
    role_id = request.form.get('role_id', type=int)
    role = Role.query.get(role_id)
    
    if role:
        user.role_id = role.id
        db.session.commit()
        flash(f'Роль пользователя "{user.username}" изменена на "{role.name}"', 'success')
    else:
        flash('Неверная роль', 'danger')
    search = request.args.get('search', '')
    return redirect(url_for('admin.users', search=request.args.get('search', '')))

@bp.route('/user/<int:user_id>/reset_password', methods=['POST'])
@login_required
def reset_password(user_id):
    """Сброс пароля пользователя (генерация временного)"""
    if not is_admin():
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('main.dashboard'))
    
    user = User.query.get_or_404(user_id)
    
    if user.is_blocked:
        flash(f'Пользователь "{user.username}" заблокирован. Сначала разблокируйте.', 'danger')
        return redirect(url_for('admin.users'))
    
    # Генерируем временный пароль
    import secrets
    import string
    
    alphabet = string.ascii_letters + string.digits
    temp_password = ''.join(secrets.choice(alphabet) for _ in range(10))
    
    user.password_hash = generate_password_hash(temp_password)
    db.session.commit()
    
    # В реальном проекте здесь отправка email
    flash(f'Пароль для пользователя "{user.username}" сброшен. Новый пароль: {temp_password}', 'info')
    
    return redirect(url_for('admin.users', search=request.args.get('search', '')))

@bp.route('/user/<int:user_id>/block', methods=['POST'])
@login_required
def block_user(user_id):
    """Блокировка/разблокировка пользователя"""
    if not is_admin():
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('main.dashboard'))
    
    user = User.query.get_or_404(user_id)
    
    # Нельзя заблокировать себя
    if user.id == current_user.id:
        flash('Нельзя заблокировать самого себя', 'warning')
        return redirect(url_for('admin.users'))
    
    # Меняем статус (нужно добавить поле is_blocked в модель User)
    user.is_blocked = not user.is_blocked
    db.session.commit()
    
    status = 'заблокирован' if user.is_blocked else 'разблокирован'
    flash(f'Пользователь "{user.username}" {status}', 'success')
    
    return redirect(url_for('admin.users', search=request.args.get('search', '')))

@bp.route('/user/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    """Удаление пользователя (с проверкой зависимостей)"""
    if not is_admin():
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('main.dashboard'))
    
    user = User.query.get_or_404(user_id)
    
    # Нельзя удалить себя
    if user.id == current_user.id:
        flash('Нельзя удалить самого себя', 'warning')
        return redirect(url_for('admin.users'))
    
    # Проверяем, есть ли у пользователя данные
    template_count = len(user.workout_templates)
    session_count = len(user.workout_sessions)
    
    if template_count > 0 or session_count > 0:
        flash(f'Пользователь "{user.username}" имеет {template_count} шаблонов и {session_count} тренировок. Сначала удалите их.', 'danger')
        return redirect(url_for('admin.users'))
    
    username = user.username
    db.session.delete(user)
    db.session.commit()
    
    flash(f'Пользователь "{username}" удалён', 'success')
    
    return redirect(url_for('admin.users', search=request.args.get('search', '')))