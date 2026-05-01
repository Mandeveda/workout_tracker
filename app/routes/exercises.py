from flask import render_template, redirect, url_for, flash, request, Blueprint
from flask_login import login_required, current_user
from flask import jsonify  # добавьте в импорт
from app import db
from app.models import Exercise, TemplateExercise
from app.forms import ExerciseForm

bp = Blueprint('exercises', __name__, url_prefix='/exercises')

def is_expert():
    """Проверка, имеет ли пользователь права эксперта"""
    return current_user.is_authenticated and current_user.role.name in ['expert', 'admin']

@bp.route('/')
@login_required
def list_exercises():
    """Список всех упражнений (с поиском и фильтрацией)"""
    search = request.args.get('search', '')
    muscle_group = request.args.get('muscle_group', '')
    
    query = Exercise.query
    
    if search:
        query = query.filter(Exercise.name.ilike(f'%{search}%'))
    
    if muscle_group:
        query = query.join(Exercise.muscle_group).filter(MuscleGroup.name == muscle_group)
    
    exercises = query.order_by(Exercise.name).all()
    
    # Получаем список групп мышц для фильтра
    from app.models import MuscleGroup
    muscle_groups = MuscleGroup.query.order_by('display_name').all()
    
    return render_template('exercises/list.html', 
                         exercises=exercises, 
                         search=search, 
                         muscle_group=muscle_group,
                         muscle_groups=muscle_groups)

@bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_exercise():
    if not is_expert():
        flash('Доступ только для экспертов и администраторов', 'danger')
        return redirect(url_for('main.dashboard'))
    
    form = ExerciseForm()
    
    if form.validate_on_submit():
        # Проверка на дубликат
        existing = Exercise.query.filter_by(name=form.name.data).first()
        if existing:
            flash('Упражнение с таким названием уже существует', 'danger')
            return render_template('exercises/add.html', form=form)
        
        # Создаём упражнение (обрабатываем 0 как None)
        exercise = Exercise(
            name=form.name.data,
            exercise_type=form.exercise_type.data,
            muscle_group_id=form.muscle_group_id.data if form.muscle_group_id.data != 0 else None,
            muscle_subgroup_id=form.muscle_subgroup_id.data if form.muscle_subgroup_id.data != 0 else None,
            description=form.description.data,
            created_by_id=current_user.id
        )
        
        db.session.add(exercise)
        db.session.commit()
        
        flash(f'Упражнение "{exercise.name}" успешно создано!', 'success')
        return redirect(url_for('exercises.list_exercises'))
    
    return render_template('exercises/add.html', form=form)

@bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_exercise(id):
    """Редактирование упражнения (только автор или админ)"""
    exercise = Exercise.query.get_or_404(id)
    
    # Проверка прав
    if not (current_user.role.name in ['admin'] or exercise.created_by_id == current_user.id):
        flash('Вы можете редактировать только свои упражнения', 'danger')
        return redirect(url_for('exercises.list_exercises'))
    
    form = ExerciseForm(obj=exercise)
    if form.validate_on_submit():
        # Проверка на дубликат (исключая текущее упражнение)
        existing = Exercise.query.filter(Exercise.name == form.name.data, Exercise.id != id).first()
        if existing:
            flash('Упражнение с таким названием уже существует', 'danger')
            return render_template('exercises/edit.html', form=form, exercise=exercise)
        
        exercise.name = form.name.data
        exercise.exercise_type = form.exercise_type.data
        exercise.muscle_group_id = form.muscle_group_id.data
        exercise.muscle_subgroup_id = form.muscle_subgroup_id.data
        exercise.description = form.description.data
        
        db.session.commit()
        flash('Упражнение обновлено', 'success')
        return redirect(url_for('exercises.list_exercises'))
    
    return render_template('exercises/edit.html', form=form, exercise=exercise)

@bp.route('/get_subgroups')
@login_required
def get_subgroups():
    """Возвращает JSON со списком уточнений для выбранной группы мышц"""
    muscle_group_id = request.args.get('muscle_group_id', type=int)
    if muscle_group_id:
        from app.models import MuscleSubgroup
        subgroups = MuscleSubgroup.query.filter_by(muscle_group_id=muscle_group_id).all()
        return jsonify([{'id': s.id, 'display_name': s.display_name} for s in subgroups])
    return jsonify([])

@bp.route('/del_exercise/<int:exercise_id>')
@login_required
def del_exercise(exercise_id):
    """Удаление упражнения из базы"""
    exercise = Exercise.query.get_or_404(exercise_id)
    if not (current_user.role.name in ['admin'] or exercise.created_by_id == current_user.id):
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('exercises.list_exercises'))
    
    template_exercise_count = TemplateExercise.query.filter_by(exercise_id=exercise_id).count()

    if template_exercise_count > 0:
        flash(f'Нельзя удалить упражнение: оно используется в {template_exercise_count} шаблонах тренировок', 'warning')
        return redirect(url_for('exercises.list_exercises'))
    
    db.session.delete(exercise)
    db.session.commit()
    flash('Упражнение удалено из базы', 'success')
    return redirect(url_for('exercises.list_exercises'))