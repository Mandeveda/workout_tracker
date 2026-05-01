from flask import render_template, redirect, url_for, flash, request, Blueprint
from flask_login import login_required, current_user
from app import db
from app.models import WorkoutTemplate, WorkoutSchedule
from app.forms import ProgramForm

bp = Blueprint('program', __name__, url_prefix='/program')

@bp.route('/create/<int:template_id>', methods=['GET', 'POST'])
@login_required
def create_program(template_id):
    """Создание программы из шаблона (выбор дней недели и генерация расписания)"""
    template = WorkoutTemplate.query.get_or_404(template_id)
    
    # Проверка прав
    if template.user_id != current_user.id:
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('templates.list_templates'))
    
    form = ProgramForm()
    
    # Динамически обновляем choices для template_id (убираем фиксацию в форме)
    from app.models import WorkoutTemplate
    form.template_id.choices = [(t.id, t.name) for t in WorkoutTemplate.query.filter_by(user_id=current_user.id).all()]
    form.template_id.data = template_id  # Предустанавливаем текущий шаблон
    
    if form.validate_on_submit():
        # Здесь будет генерация расписания
        flash('Функция генерации расписания будет реализована в следующем шаге', 'info')
        return redirect(url_for('templates.list_templates'))
    
    return render_template('program/create.html', form=form, template=template)