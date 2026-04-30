from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError
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