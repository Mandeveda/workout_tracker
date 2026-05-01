from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, TextAreaField, IntegerField, FloatField, BooleanField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError, NumberRange
# Временно убираем Email
from app.models import User

class RegistrationForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField('Email', validators=[DataRequired()])  # Убрали Email() валидатор
    password = PasswordField('Пароль', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Подтвердите пароль', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Зарегистрироваться')
    
    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('Это имя уже занято')
    
    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Этот email уже зарегистрирован')

class LoginForm(FlaskForm):
    username = StringField('Логин или Email', validators=[DataRequired()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    submit = SubmitField('Войти')

class ExerciseForm(FlaskForm):
    name = StringField('Название упражнения', validators=[DataRequired(), Length(max=100)])
    exercise_type = SelectField('Тип упражнения', choices=[
        ('strength', 'Силовое (с весом)'),
        ('bodyweight', 'Собственный вес'),
        ('cardio', 'Кардио')
    ], validators=[DataRequired()])
    
    muscle_group_id = SelectField('Группа мышц', coerce=int, choices=[])
    muscle_subgroup_id = SelectField('Уточнение', coerce=int, choices=[])
    
    description = TextAreaField('Описание техники выполнения')
    submit = SubmitField('Создать упражнение')
    
    def __init__(self, *args, **kwargs):
        super(ExerciseForm, self).__init__(*args, **kwargs)
        from app.models import MuscleGroup, MuscleSubgroup
        
        # Загружаем группы мышц
        groups = MuscleGroup.query.order_by('display_name').all()
        self.muscle_group_id.choices = [(0, 'Не выбрано')] + [(g.id, g.display_name) for g in groups]
        
        # Загружаем ВСЕ уточнения для валидации (WTForms требует, чтобы значение было в choices)
        all_subgroups = MuscleSubgroup.query.all()
        self.muscle_subgroup_id.choices = [(0, 'Не выбрано')] + [(s.id, s.display_name) for s in all_subgroups]

class WorkoutTemplateForm(FlaskForm):
    name = StringField('Название шаблона', validators=[DataRequired(), Length(max=100)])
    submit = SubmitField('Создать шаблон')

class TemplateExerciseForm(FlaskForm):
    exercise_id = SelectField('Упражнение', coerce=int, validators=[DataRequired()])
    order = IntegerField('Порядок выполнения', default=0)
    submit = SubmitField('Добавить упражнение')
    
    def __init__(self, *args, **kwargs):
        super(TemplateExerciseForm, self).__init__(*args, **kwargs)
        from app.models import Exercise
        self.exercise_id.choices = [(e.id, e.name) for e in Exercise.query.order_by('name').all()]

class ProgramForm(FlaskForm):
    """Форма для создания программы (расписания с параметрами)"""
    template_id = SelectField('Выберите шаблон', coerce=int, validators=[DataRequired()])
    
    # Дни недели (множественный выбор)
    monday = BooleanField('Понедельник')
    tuesday = BooleanField('Вторник')
    wednesday = BooleanField('Среда')
    thursday = BooleanField('Четверг')
    friday = BooleanField('Пятница')
    saturday = BooleanField('Суббота')
    sunday = BooleanField('Воскресенье')
    
    weeks = SelectField('Количество недель', choices=[(1, '1 неделя'), (2, '2 недели'), (4, '4 недели'), (8, '8 недель')], coerce=int, default=4)
    
    submit = SubmitField('Сгенерировать расписание')
    
    def __init__(self, *args, **kwargs):
        super(ProgramForm, self).__init__(*args, **kwargs)
        from app.models import WorkoutTemplate
        self.template_id.choices = [(0, 'Выберите шаблон')] + [(t.id, t.name) for t in WorkoutTemplate.query.filter_by(user_id=current_user.id).all()]

class SetParametersForm(FlaskForm):
    """Форма для заполнения параметров упражнения в расписании"""
    sets = IntegerField('Количество подходов', validators=[DataRequired(), NumberRange(min=1, max=10)])
    reps = IntegerField('Количество повторений', validators=[DataRequired(), NumberRange(min=1, max=100)])
    weight = FloatField('Вес (кг)', default=0)
    duration = IntegerField('Длительность (мин)', default=0)  # для кардио
    distance = FloatField('Дистанция (км)', default=0)  # для кардио
    submit = SubmitField('Сохранить параметры')