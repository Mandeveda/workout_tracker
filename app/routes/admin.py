from flask import render_template, redirect, url_for, flash, request, Blueprint
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from app import db
from app.models import User, Role
from sqlalchemy import or_

bp = Blueprint('admin', __name__, url_prefix='/admin')

def back_to_list():
    """Вернуться к списку с тем же поиском, фильтром и страницей"""
    return redirect(url_for('admin.users',
                            search=request.args.get('search', ''),
                            show=request.args.get('show', 'all'),
                            page=request.args.get('page', 1, type=int)))

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
    
    # Поиск и фильтр: show = all | имя роли | blocked
    search = request.args.get('search', '')
    show = request.args.get('show', 'all')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    roles = Role.query.order_by(Role.id).all()
    
    base = User.query
    if search:
        base = base.filter(
            or_(
                User.username.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%')
            )
        )
    
    # Вкладки фильтра с количеством (с учётом поиска)
    filters = [{'key': 'all', 'count': base.count()}]
    # По уровню доступа: администраторы, эксперты, пользователи, затем прочие роли
    level = {'admin': 0, 'expert': 1, 'user': 2}
    for role in sorted(roles, key=lambda r: level.get(r.name, 9)):
        filters.append({'key': role.name, 'count': base.filter(User.role_id == role.id).count()})
    filters.append({'key': 'blocked', 'count': base.filter(User.is_blocked.is_(True)).count()})
    
    query = base
    if show == 'blocked':
        query = query.filter(User.is_blocked.is_(True))
    elif show != 'all':
        role = next((r for r in roles if r.name == show), None)
        if role:
            query = query.filter(User.role_id == role.id)
        else:
            show = 'all'
    
    users = query.order_by(User.id).paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin/users.html', users=users, roles=roles, search=search, show=show, filters=filters)

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
        return back_to_list()
    
    role_id = request.form.get('role_id', type=int)
    role = Role.query.get(role_id)
    
    if role:
        user.role_id = role.id
        db.session.commit()
        flash(f'Роль пользователя "{user.username}" изменена на "{role.name}"', 'success')
    else:
        flash('Неверная роль', 'danger')
    return back_to_list()

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
        return back_to_list()
    
    # Генерируем временный пароль
    import secrets
    import string
    
    alphabet = string.ascii_letters + string.digits
    temp_password = ''.join(secrets.choice(alphabet) for _ in range(10))
    
    user.password_hash = generate_password_hash(temp_password)
    db.session.commit()
    
    # В реальном проекте здесь отправка email
    flash(f'Пароль для пользователя "{user.username}" сброшен. Новый пароль: {temp_password}', 'info')
    
    return back_to_list()

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
        return back_to_list()
    
    # Меняем статус (нужно добавить поле is_blocked в модель User)
    user.is_blocked = not user.is_blocked
    db.session.commit()
    
    status = 'заблокирован' if user.is_blocked else 'разблокирован'
    flash(f'Пользователь "{user.username}" {status}', 'success')
    
    return back_to_list()

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
        return back_to_list()
    
    # Проверяем, есть ли у пользователя данные
    template_count = len(user.workout_templates)
    session_count = len(user.workout_sessions)
    
    if template_count > 0 or session_count > 0:
        flash(f'Пользователь "{user.username}" имеет {template_count} шаблонов и {session_count} тренировок. Сначала удалите их.', 'danger')
        return back_to_list()
    
    username = user.username
    db.session.delete(user)
    db.session.commit()
    
    flash(f'Пользователь "{username}" удалён', 'success')
    
    return back_to_list()