from flask import render_template, redirect, url_for, flash, request, Blueprint, current_app
from flask_login import login_required, current_user
from app import db, deletion
from app.models import WorkoutTemplate, TemplateExercise, WorkoutSchedule, Exercise, User
from sqlalchemy import func
from app.forms import WorkoutTemplateForm, AddExerciseForm
from app.textutil import plural

bp = Blueprint('templates', __name__, url_prefix='/templates')

@bp.route('/')
@login_required
def list_templates():
    """Список шаблонов (админ видит все, обычный пользователь — только свои)"""
    if current_user.role.name == 'admin':
        # Админ видит все шаблоны; фильтр ?owner=<id пользователя>
        owners = (db.session.query(User, func.count(WorkoutTemplate.id))
                  .join(WorkoutTemplate, WorkoutTemplate.user_id == User.id)
                  .group_by(User.id).order_by(func.lower(User.username)).all())
        owner_id = request.args.get('owner', type=int)
        if owner_id not in {user.id for user, _ in owners}:
            owner_id = None
        query = WorkoutTemplate.query
        if owner_id:
            query = query.filter_by(user_id=owner_id)
        templates = query.order_by(WorkoutTemplate.created_at.desc()).all()
        return render_template('templates/list.html', templates=templates, owners=owners, owner_id=owner_id)

    # Обычный пользователь видит только свои
    templates = WorkoutTemplate.query.filter_by(
        user_id=current_user.id, 
        is_active=True
    ).order_by(WorkoutTemplate.created_at.desc()).all()
    return render_template('templates/list.html', templates=templates)

@bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_template():
    """Создание нового шаблона"""
    form = WorkoutTemplateForm()
    if form.validate_on_submit():
        template = WorkoutTemplate(
            name=form.name.data,
            user_id=current_user.id
        )
        db.session.add(template)
        db.session.commit()
        flash(f'Шаблон "{template.name}" создан!', 'success')
        return redirect(url_for('templates.edit_template', template_id=template.id))
    return render_template('templates/create.html', form=form)

@bp.route('/edit/<int:template_id>', methods=['GET', 'POST'])
@login_required
def edit_template(template_id):
    """Редактирование шаблона"""
    template = WorkoutTemplate.query.get_or_404(template_id)
    
    if not current_user.can_edit(template):
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('templates.list_templates'))
    
    # Обработка POST запроса для редактирования имени
    if request.method == 'POST' and 'edit_name' in request.form:
        new_name = (request.form.get('name') or '').strip()
        if len(new_name) > 100:
            flash('Название — не длиннее 100 символов', 'danger')
        elif new_name:
            template.name = new_name
            db.session.commit()
            flash('Название шаблона обновлено', 'success')
        return redirect(url_for('templates.edit_template', template_id=template.id))
    
    template_exercises = TemplateExercise.query.filter_by(template_id=template.id).order_by(TemplateExercise.order).all()
    
    return render_template('templates/edit.html', template=template, template_exercises=template_exercises)

@bp.route('/add_exercise/<int:template_id>', methods=['GET', 'POST'])
@login_required
def add_exercise(template_id):
    """Добавление упражнений в шаблон с фильтрацией (групповое)"""
    
    template = WorkoutTemplate.query.get_or_404(template_id)
    
    if not current_user.can_edit(template):
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('templates.list_templates'))
    
    form = AddExerciseForm()
    
    # Получаем параметры фильтрации из GET-запроса
    search = request.args.get('search', '')
    exercise_type = request.args.get('type', '')
    muscle_group_id = request.args.get('muscle_group', 0, type=int)
    subgroup_id = request.args.get('subgroup', 0, type=int)
    
    # Строим запрос с фильтрами
    query = Exercise.query
    
    if search:
        query = query.filter(Exercise.name.ilike(f'%{search}%'))
    if exercise_type:
        query = query.filter(Exercise.exercise_type == exercise_type)
    if muscle_group_id:
        query = query.filter(Exercise.muscle_group_id == muscle_group_id)
    if subgroup_id:
        query = query.filter(Exercise.muscle_subgroup_id == subgroup_id)
    
    # Получаем список упражнений
    exercises = query.order_by(Exercise.name).all()
    
    # Обновляем choices для формы
    exercise_choices = [(e.id, e.name) for e in exercises]
    form.exercise_ids.choices = exercise_choices
    
    if form.validate_on_submit():
        selected_ids = form.exercise_ids.data
        
        if not selected_ids:
            flash('Выберите хотя бы одно упражнение', 'warning')
        else:
            # Получаем максимальный order
            max_order = db.session.query(func.max(TemplateExercise.order)).filter_by(template_id=template.id).scalar()
            if max_order is None:
                max_order = -1
            
            added_count = 0
            skipped_count = 0
            
            for exercise_id in selected_ids:
                # Проверка на дубликат
                existing = TemplateExercise.query.filter_by(
                    template_id=template.id,
                    exercise_id=exercise_id
                ).first()
                
                if existing:
                    skipped_count += 1
                    continue
                
                max_order += 1
                template_exercise = TemplateExercise(
                    template_id=template.id,
                    exercise_id=exercise_id,
                    order=max_order
                )
                db.session.add(template_exercise)
                added_count += 1
            
            db.session.commit()
            
            if added_count > 0:
                flash(f'Добавлено {added_count} упражнений', 'success')
            if skipped_count > 0:
                flash(f'{skipped_count} упражнений уже были в шаблоне', 'warning')
        
        return redirect(url_for('templates.edit_template', template_id=template.id))
    
    return render_template('templates/add_exercise.html', 
                         form=form, 
                         template=template,
                         exercises=exercises)

@bp.route('/delete_exercise/<int:template_id>/<int:exercise_id>', methods=['POST'])
@login_required
def delete_exercise(template_id, exercise_id):
    """Удаление упражнения из шаблона"""
    template_exercise = TemplateExercise.query.get_or_404(exercise_id)
    
    # проверяем шаблон, к которому относится упражнение
    if not current_user.can_edit(template_exercise.template):
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('templates.list_templates'))
    
    template_id = template_exercise.template_id
    db.session.delete(template_exercise)
    db.session.commit()
    flash('Упражнение удалено из шаблона', 'success')
    return redirect(url_for('templates.edit_template', template_id=template_id))

@bp.route('/move_up/<int:template_id>/<int:exercise_id>', methods=['POST'])
@login_required
def move_up_exercise(template_id, exercise_id):
    """Переместить упражнение вверх по порядку"""
    template_exercise = TemplateExercise.query.get_or_404(exercise_id)
    
    if not current_user.can_edit(template_exercise.template):
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('templates.list_templates'))
    
    # template_id берём из самого упражнения, а не из URL: иначе можно подставить
    # чужой шаблон и поменять порядок его упражнений
    template_id = template_exercise.template_id
    
    # Находим предыдущее упражнение (с меньшим order)
    prev = TemplateExercise.query.filter(
        TemplateExercise.template_id == template_id,
        TemplateExercise.order < template_exercise.order
    ).order_by(TemplateExercise.order.desc()).first()
    
    if prev:
        # Меняем значения order
        old_order = template_exercise.order
        template_exercise.order = prev.order
        prev.order = old_order
        
        # Добавляем оба объекта в сессию и коммитим
        db.session.add(template_exercise)
        db.session.add(prev)
        db.session.commit()
        flash('Порядок упражнений изменён', 'success')
    else:
        flash('Это упражнение уже первое', 'info')
    
    return redirect(url_for('templates.edit_template', template_id=template_id))

@bp.route('/move_down/<int:template_id>/<int:exercise_id>', methods=['POST'])
@login_required
def move_down_exercise(template_id, exercise_id):
    """Переместить упражнение вниз по порядку"""
    template_exercise = TemplateExercise.query.get_or_404(exercise_id)
    
    if not current_user.can_edit(template_exercise.template):
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('templates.list_templates'))
    
    # template_id берём из самого упражнения, а не из URL (см. move_up_exercise)
    template_id = template_exercise.template_id
    
    # Находим следующее упражнение (с большим order)
    next_ex = TemplateExercise.query.filter(
        TemplateExercise.template_id == template_id,
        TemplateExercise.order > template_exercise.order
    ).order_by(TemplateExercise.order.asc()).first()
    
    if next_ex:
        # Меняем значения order
        old_order = template_exercise.order
        template_exercise.order = next_ex.order
        next_ex.order = old_order
        
        # Добавляем оба объекта в сессию и коммитим
        db.session.add(template_exercise)
        db.session.add(next_ex)
        db.session.commit()
        flash('Порядок упражнений изменён', 'success')
    else:
        flash('Это упражнение уже последнее', 'info')
    
    return redirect(url_for('templates.edit_template', template_id=template_id))

@bp.route('/delete/<int:template_id>', methods=['POST'])
@login_required
def delete_template(template_id):
    """Удаление шаблона (владелец или админ): начатые тренировки остаются в истории,
    дни расписания без них удаляются"""
    template = WorkoutTemplate.query.get_or_404(template_id)
    
    if not current_user.can_edit(template):
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('templates.list_templates'))
    
    template_name = template.name
    preview = deletion.template_deletion_preview(template)
    try:
        deletion.delete_template(template)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Ошибка удаления шаблона %s', template_id)
        flash('Не удалось удалить шаблон. Попробуйте ещё раз.', 'danger')
        return redirect(url_for('templates.list_templates'))
    
    details = []
    if preview['removed_days']:
        details.append(f"из расписания убрано {preview['removed_days']} "
                       f"{plural(preview['removed_days'], 'день', 'дня', 'дней')}")
    if preview['kept_sessions']:
        details.append(f"{preview['kept_sessions']} "
                       f"{plural(preview['kept_sessions'], 'тренировка осталась', 'тренировки остались', 'тренировок остались')} в истории")
    flash(f'Шаблон «{template_name}» удалён' + (': ' + ', '.join(details) if details else '') + '.', 'success')
    return redirect(url_for('templates.list_templates'))

@bp.route('/archive/<int:template_id>', methods=['POST'])
@login_required
def archive_template(template_id):
    """Архивация шаблона (делаем неактивным)"""
    template = WorkoutTemplate.query.get_or_404(template_id)
    
    if not current_user.can_edit(template):
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('templates.list_templates'))
    
    # Проверка: есть ли активные расписания с этим шаблоном
    active_schedules = WorkoutSchedule.query.filter_by(
        template_id=template.id,
        status='planned'
    ).count()
    
    if active_schedules > 0:
        flash(f'Нельзя архивировать шаблон "{template.name}", так как есть {active_schedules} активных тренировок по нему', 'danger')
        return redirect(url_for('templates.list_templates'))
    
    template.is_active = False
    db.session.commit()
    flash(f'Шаблон "{template.name}" архивирован (скрыт из списка активных)', 'success')
    return redirect(url_for('templates.list_templates'))

@bp.route('/restore/<int:template_id>', methods=['POST'])
@login_required
def restore_template(template_id):
    """Восстановление шаблона из архива"""
    template = WorkoutTemplate.query.get_or_404(template_id)
    
    if not current_user.can_edit(template):
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('templates.list_templates'))
    
    template.is_active = True
    db.session.commit()
    flash(f'Шаблон "{template.name}" восстановлен', 'success')
    return redirect(url_for('templates.list_templates'))

@bp.route('/archived')
@login_required
def archived_templates():
    """Список архивированных (неактивных) шаблонов"""
    if current_user.role.name == 'admin':
        templates = WorkoutTemplate.query.filter_by(is_active=False).order_by(WorkoutTemplate.created_at.desc()).all()
    else:
        templates = WorkoutTemplate.query.filter_by(
            user_id=current_user.id, 
            is_active=False
        ).order_by(WorkoutTemplate.created_at.desc()).all()
    
    return render_template('templates/archived.html', templates=templates)