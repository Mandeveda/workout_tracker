from flask_wtf import FlaskForm
from flask_login import current_user
from wtforms import StringField, PasswordField, SubmitField, SelectField, TextAreaField, IntegerField, FloatField, BooleanField, DateField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError, NumberRange
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
    
    # Для силовых и bodyweight
    muscle_group_id = SelectField('Группа мышц', coerce=int, choices=[])
    muscle_subgroup_id = SelectField('Уточнение', coerce=int, choices=[])
    
    description = TextAreaField('Описание техники выполнения')

    media_type = SelectField('Тип медиа', choices=[
        ('none', 'Без изображения/видео'),
        ('image', 'Изображение (JPG, PNG)'),
        ('gif', 'GIF-анимация'),
        ('youtube', 'YouTube видео')
    ], default='none')
    media_url = StringField('Ссылка на изображение/GIF', validators=[Length(max=500)])
    youtube_id = StringField('ID YouTube видео', validators=[Length(max=20)])
    
    submit = SubmitField('Создать упражнение')
    
    def __init__(self, *args, **kwargs):
        super(ExerciseForm, self).__init__(*args, **kwargs)
        from app.models import MuscleGroup, MuscleSubgroup
        
        groups = MuscleGroup.query.order_by('display_name').all()
        self.muscle_group_id.choices = [(0, 'Не выбрано')] + [(g.id, g.display_name) for g in groups]
        
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

class ExerciseParametersForm(FlaskForm):
    """Форма для параметров одного упражнения (динамическая)"""
    input_type = SelectField('Тип нагрузки', choices=[
        ('fixed', 'Одинаково во всех подходах'),
        ('progressive', 'Индивидуально для каждого подхода')
    ], validators=[DataRequired()])
    
    # Для fixed режима
    sets = IntegerField('Количество подходов', default=3, validators=[NumberRange(min=1, max=20)])
    reps = IntegerField('Повторений в подходе', default=10, validators=[NumberRange(min=1, max=100)])
    weight = FloatField('Вес (кг)', default=0)
    
    # Для progressive режима (будет динамически добавляться через JS)
    # Храним как строку JSON в отдельном поле
    
    def __init__(self, *args, **kwargs):
        super(ExerciseParametersForm, self).__init__(*args, **kwargs)
        # Убираем валидацию для progressive режима
        self.sets.validators = []
        self.reps.validators = []
        self.weight.validators = []

class ProgramGenerationForm(FlaskForm):
    """Форма для генерации программы"""
    template_id = SelectField('Шаблон тренировки', coerce=int, validators=[DataRequired()])
    
    # Дни недели
    monday = BooleanField('Понедельник')
    tuesday = BooleanField('Вторник')
    wednesday = BooleanField('Среда')
    thursday = BooleanField('Четверг')
    friday = BooleanField('Пятница')
    saturday = BooleanField('Суббота')
    sunday = BooleanField('Воскресенье')
    
    # Период действия
    start_date = DateField('Дата начала', validators=[DataRequired()], format='%Y-%m-%d')
    end_date = DateField('Дата окончания', validators=[DataRequired()], format='%Y-%m-%d')
    
    submit = SubmitField('Продолжить')
    
    def __init__(self, *args, **kwargs):
        super(ProgramGenerationForm, self).__init__(*args, **kwargs)
        from app.models import WorkoutTemplate
        from flask_login import current_user
        self.template_id.choices = [(0, 'Выберите шаблон')] + [(t.id, t.name) for t in WorkoutTemplate.query.filter_by(user_id=current_user.id).all()]

class ProfileForm(FlaskForm):
    """Форма редактирования профиля"""
    username = StringField('Имя пользователя', validators=[DataRequired(), Length(min=3, max=80)])
    weight = FloatField('Вес (кг)', validators=[NumberRange(min=30, max=300)], default=70)
    height = FloatField('Рост (см)', validators=[NumberRange(min=100, max=250)], default=170)
    age = IntegerField('Возраст', validators=[NumberRange(min=10, max=120)], default=25)
    gender = SelectField('Пол', choices=[('male', 'Мужской'), ('female', 'Женский')])
    
    # Антропометрия
    chest_circumference = FloatField('Грудь (см)', validators=[NumberRange(min=0, max=200)], default=0)
    waist_circumference = FloatField('Талия (см)', validators=[NumberRange(min=0, max=200)], default=0)
    hips_circumference = FloatField('Бёдра (см)', validators=[NumberRange(min=0, max=200)], default=0)
    biceps_circumference = FloatField('Бицепс (см)', validators=[NumberRange(min=0, max=100)], default=0)
    forearm_circumference = FloatField('Предплечье (см)', validators=[NumberRange(min=0, max=100)], default=0)
    thigh_circumference = FloatField('Бедро (см)', validators=[NumberRange(min=0, max=150)], default=0)
    calf_circumference = FloatField('Икра (см)', validators=[NumberRange(min=0, max=100)], default=0)
    neck_circumference = FloatField('Шея (см)', validators=[NumberRange(min=0, max=100)], default=0)
    
    submit = SubmitField('Сохранить изменения')

class MeasurementForm(FlaskForm):
    """Форма для добавления нового измерения"""
    weight = FloatField('Вес (кг)', validators=[NumberRange(min=30, max=300)])
    chest_circumference = FloatField('Грудь (см)', validators=[NumberRange(min=0, max=200)], default=0)
    waist_circumference = FloatField('Талия (см)', validators=[NumberRange(min=0, max=200)], default=0)
    hips_circumference = FloatField('Бёдра (см)', validators=[NumberRange(min=0, max=200)], default=0)
    biceps_circumference = FloatField('Бицепс (см)', validators=[NumberRange(min=0, max=100)], default=0)
    forearm_circumference = FloatField('Предплечье (см)', validators=[NumberRange(min=0, max=100)], default=0)
    thigh_circumference = FloatField('Бедро (см)', validators=[NumberRange(min=0, max=150)], default=0)
    calf_circumference = FloatField('Икра (см)', validators=[NumberRange(min=0, max=100)], default=0)
    neck_circumference = FloatField('Шея (см)', validators=[NumberRange(min=0, max=100)], default=0)
    submit = SubmitField('Сохранить измерение')

class ChangePasswordForm(FlaskForm):
    old_password = PasswordField('Текущий пароль', validators=[DataRequired()])
    new_password = PasswordField('Новый пароль', validators=[
        DataRequired(),
        Length(min=6, message='Пароль должен быть не менее 6 символов')
    ])
    confirm_password = PasswordField('Подтвердите пароль', validators=[
        DataRequired(),
        EqualTo('new_password', message='Пароли должны совпадать')
    ])
    submit = SubmitField('Сменить пароль')