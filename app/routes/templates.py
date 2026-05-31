from flask import render_template, redirect, url_for, flash, request, Blueprint
from flask_login import login_required, current_user
from app import db
from app.models import WorkoutTemplate, TemplateExercise, WorkoutSchedule
from app.forms import WorkoutTemplateForm, TemplateExerciseForm

bp = Blueprint('templates', __name__, url_prefix='/templates')

@bp.route('/')
@login_required
def list_templates():
    """Список шаблонов (админ видит все, обычный пользователь — только свои)"""
    if current_user.role.name == 'admin':
        # Админ видит все шаблоны
        templates = WorkoutTemplate.query.order_by(WorkoutTemplate.created_at.desc()).all()
    else:
        # Обычный пользователь видит только свои
        templates = WorkoutTemplate.query.filter_by(user_id=current_user.id).order_by(WorkoutTemplate.created_at.desc()).all()
    
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
        new_name = request.form.get('name')
        if new_name:
            template.name = new_name
            db.session.commit()
            flash('Название шаблона обновлено', 'success')
        return redirect(url_for('templates.edit_template', template_id=template.id))
    
    form = TemplateExerciseForm()
    template_exercises = TemplateExercise.query.filter_by(template_id=template.id).order_by(TemplateExercise.order).all()
    
    return render_template('templates/edit.html', template=template, template_exercises=template_exercises, form=form)

@bp.route('/add_exercise/<int:template_id>', methods=['GET', 'POST'])
@login_required
def add_exercise(template_id):
    """Добавление упражнения в шаблон"""
    template = WorkoutTemplate.query.get_or_404(template_id)
    if not current_user.can_edit(template):
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('templates.list_templates'))
    
    form = TemplateExerciseForm()
    if form.validate_on_submit():
        # Проверка на дубликат
        existing = TemplateExercise.query.filter_by(
            template_id=template.id,
            exercise_id=form.exercise_id.data
        ).first()
        
        if existing:
            flash('Это упражнение уже есть в шаблоне', 'danger')
        else:
            template_exercise = TemplateExercise(
                template_id=template.id,
                exercise_id=form.exercise_id.data,
                order=form.order.data
            )
            db.session.add(template_exercise)
            db.session.commit()
            flash('Упражнение добавлено', 'success')
        
        return redirect(url_for('templates.edit_template', template_id=template.id))
    
    return render_template('templates/add_exercise.html', form=form, template=template)

@bp.route('/delete_exercise/<int:template_id>/<int:exercise_id>')
@login_required
def delete_exercise(template_id, exercise_id):
    """Удаление упражнения из шаблона"""
    template_exercise = TemplateExercise.query.get_or_404(exercise_id)
    
    # проверяем шаблон, к которому относится упражнение
    if not current_user.can_edit(template_exercise.template):
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('templates.list_templates'))
    
    db.session.delete(template_exercise)
    db.session.commit()
    flash('Упражнение удалено из шаблона', 'success')
    return redirect(url_for('templates.edit_template', template_id=template_id))

@bp.route('/move_up/<int:template_id>/<int:exercise_id>')
@login_required
def move_up_exercise(template_id, exercise_id):
    """Переместить упражнение вверх по порядку"""
    template_exercise = TemplateExercise.query.get_or_404(exercise_id)
    
    if not current_user.can_edit(template_exercise.template):
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('templates.list_templates'))
    
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

@bp.route('/move_down/<int:template_id>/<int:exercise_id>')
@login_required
def move_down_exercise(template_id, exercise_id):
    """Переместить упражнение вниз по порядку"""
    template_exercise = TemplateExercise.query.get_or_404(exercise_id)
    
    if not current_user.can_edit(template_exercise.template):
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('templates.list_templates'))
    
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

@bp.route('/delete/<int:template_id>')
@login_required
def delete_template(template_id):
    """Удаление шаблона с проверкой"""
    template = WorkoutTemplate.query.get_or_404(template_id)
    
    # Проверка прав
    if not current_user.can_edit(template):
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('templates.list_templates'))
    
    # Проверка: есть ли упражнения в шаблоне
    exercises_count = TemplateExercise.query.filter_by(template_id=template.id).count()
    if exercises_count > 0:
        flash(f'Невозможно удалить шаблон "{template.name}". Сначала удалите все упражнения из шаблона.', 'danger')
        return redirect(url_for('templates.edit_template', template_id=template.id))
    
    # Проверка: есть ли расписания, использующие этот шаблон
    schedules_count = WorkoutSchedule.query.filter_by(template_id=template.id).count()
    if schedules_count > 0:
        flash(f'Невозможно удалить шаблон "{template.name}". Сначала удалите все программы (расписания), созданные из этого шаблона.', 'danger')
        return redirect(url_for('templates.list_templates'))
    
    # Удаляем шаблон
    template_name = template.name
    db.session.delete(template)
    db.session.commit()
    flash(f'Шаблон "{template_name}" успешно удалён!', 'success')
    
    return redirect(url_for('templates.list_templates'))