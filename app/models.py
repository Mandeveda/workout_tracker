from app import db, login_manager
from flask_login import UserMixin
from datetime import datetime
from sqlalchemy.orm import relationship

# Загрузка пользователя для Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Таблица ролей (простая, одна роль на пользователя)
class Role(db.Model):
    __tablename__ = 'roles'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200))
    
    # Отношение: у одной роли может быть много пользователей
    users = relationship('User', back_populates='role')
    
    def __repr__(self):
        return f'<Role {self.name}>'

# Пользователь
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))  # будет хранить хеш пароля
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Внешний ключ на роль (одна роль у пользователя)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False, default=2)  # 2 = обычный пользователь по умолчанию
    
    # Связи
    role = relationship('Role', back_populates='users')
    workout_templates = relationship('WorkoutTemplate', back_populates='user', cascade='all, delete-orphan')
    workout_sessions = relationship('WorkoutSession', back_populates='user', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<User {self.username}>'

# Упражнение (глобальная база)
class Exercise(db.Model):
    __tablename__ = 'exercises'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    exercise_type = db.Column(db.String(20), nullable=False)  # 'strength', 'cardio', 'bodyweight'
    description = db.Column(db.Text)
    
    # Кто добавил упражнение (эксперт)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_by = relationship('User')
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Связь с шаблонами
    template_exercises = relationship('TemplateExercise', back_populates='exercise')
    
    def __repr__(self):
        return f'<Exercise {self.name}>'

# Шаблон тренировки (план)
class WorkoutTemplate(db.Model):
    __tablename__ = 'workout_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Для привязки к дате/дню недели
    scheduled_date = db.Column(db.Date, nullable=True)  # если привязано к конкретной дате
    scheduled_weekday = db.Column(db.Integer, nullable=True)  # 0-6 (пн=0, вс=6)
    
    # Связи
    user = relationship('User', back_populates='workout_templates')
    template_exercises = relationship('TemplateExercise', back_populates='template', cascade='all, delete-orphan')
    workout_sessions = relationship('WorkoutSession', back_populates='template')
    
    def __repr__(self):
        return f'<WorkoutTemplate {self.name}>'

# Упражнение в шаблоне (с заданными параметрами)
class TemplateExercise(db.Model):
    __tablename__ = 'template_exercises'
    
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('workout_templates.id'), nullable=False)
    exercise_id = db.Column(db.Integer, db.ForeignKey('exercises.id'), nullable=False)
    order = db.Column(db.Integer, default=0)  # порядок выполнения
    
    # Параметры для силовых/bodyweight
    planned_sets = db.Column(db.Integer)
    planned_reps = db.Column(db.Integer)
    planned_weight = db.Column(db.Float)  # в кг
    
    # Параметры для кардио
    planned_duration = db.Column(db.Integer)  # в минутах
    planned_distance = db.Column(db.Float)  # в км
    planned_target_heart_rate = db.Column(db.Integer)  # целевой пульс
    
    # Связи
    template = relationship('WorkoutTemplate', back_populates='template_exercises')
    exercise = relationship('Exercise', back_populates='template_exercises')
    
    # Логи выполнения (связь)
    set_logs = relationship('SetLog', back_populates='template_exercise', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<TemplateExercise {self.exercise.name} in template {self.template.name}>'

# Сессия тренировки (фактическое выполнение)
class WorkoutSession(db.Model):
    __tablename__ = 'workout_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey('workout_templates.id'), nullable=True)  # NULL если ручная тренировка
    date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Статус тренировки
    status = db.Column(db.String(20), default='planned')  # planned, completed, skipped, postponed
    
    # Общая оценка выполнения
    completion_percent = db.Column(db.Float, default=0.0)
    
    # Связи
    user = relationship('User', back_populates='workout_sessions')
    template = relationship('WorkoutTemplate', back_populates='workout_sessions')
    set_logs = relationship('SetLog', back_populates='session', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<WorkoutSession {self.date} completion={self.completion_percent}%>'

# Лог каждого подхода (или кардио-сегмента)
class SetLog(db.Model):
    __tablename__ = 'set_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('workout_sessions.id'), nullable=False)
    template_exercise_id = db.Column(db.Integer, db.ForeignKey('template_exercises.id'), nullable=True)  # NULL если ручное упражнение
    
    # Фактические данные
    set_number = db.Column(db.Integer)  # номер подхода (1, 2, 3...)
    
    # Для силовых/bodyweight
    actual_reps = db.Column(db.Integer)
    actual_weight = db.Column(db.Float)
    
    # Для кардио
    actual_duration = db.Column(db.Integer)  # минут
    actual_distance = db.Column(db.Float)  # км
    actual_heart_rate = db.Column(db.Integer)  # средний/макс пульс
    
    # Процент выполнения этого подхода
    completion_percent = db.Column(db.Float, default=0.0)
    
    # Связи
    session = relationship('WorkoutSession', back_populates='set_logs')
    template_exercise = relationship('TemplateExercise', back_populates='set_logs')
    
    def __repr__(self):
        return f'<SetLog set={self.set_number} completion={self.completion_percent}%>'