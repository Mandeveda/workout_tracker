from flask import render_template, redirect, url_for, flash, request, Blueprint, current_app
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from app import db, deletion
from app.models import User, Role
from sqlalchemy import or_
from app.timeutil import utcnow

bp = Blueprint('admin', __name__, url_prefix='/admin')

def back_to_list():
    """Вернуться к списку с тем же поиском, фильтром и страницей"""
    return redirect(url_for('admin.users', **list_args()))

def list_args():
    """Поиск, фильтр и страница списка — чтобы вернуться туда же"""
    return {'search': request.args.get('search', ''), 'show': request.args.get('show', 'all'),
            'page': request.args.get('page', 1, type=int)}

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
    unconfirmed = base.filter(User.email_confirmed_at.is_(None))
    filters.append({'key': 'unconfirmed', 'count': unconfirmed.count()})
    filters.append({'key': 'overdue', 'count': unconfirmed.filter(User.email_confirm_deadline < utcnow()).count()})
    
    query = base
    if show == 'blocked':
        query = query.filter(User.is_blocked.is_(True))
    elif show == 'unconfirmed':
        query = query.filter(User.email_confirmed_at.is_(None))
    elif show == 'overdue':
        query = query.filter(User.email_confirmed_at.is_(None), User.email_confirm_deadline < utcnow())
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

@bp.route('/user/<int:user_id>/delete', methods=['GET', 'POST'])
@login_required
def delete_user(user_id):
    """Удаление пользователя со всеми данными: GET — перечень того, что пропадёт, POST — удаление
    после ввода имени пользователя"""
    if not is_admin():
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('main.dashboard'))
    
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Нельзя удалить самого себя', 'warning')
        return back_to_list()
    if user.role.name == 'admin':
        flash(f'«{user.username}» — администратор. Сначала смените ему роль, потом удаляйте.', 'warning')
        return back_to_list()
    
    if request.method == 'POST':
        if request.form.get('confirm_username', '').strip() != user.username:
            flash('Имя введено неверно — аккаунт не удалён.', 'danger')
            return redirect(url_for('admin.delete_user', user_id=user.id, **list_args()))
        username = user.username
        try:
            deletion.delete_user(user, heir=current_user)
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Ошибка удаления пользователя %s', user_id)
            flash('Не удалось удалить пользователя. Попробуйте ещё раз.', 'danger')
            return back_to_list()
        flash(f'Пользователь «{username}» и все его данные удалены', 'success')
        return back_to_list()
    
    return render_template('admin/delete_user.html', user=user, keep=list_args(),
                           preview=deletion.user_deletion_preview(user))
