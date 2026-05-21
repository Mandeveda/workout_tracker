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
    is_blocked = db.Column(db.Boolean, default=False)
    
    # Внешний ключ на роль (одна роль у пользователя)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False, default=2)  # 2 = обычный пользователь по умолчанию
    
    # Антропометрические данные
    weight = db.Column(db.Float, default=70.0)  # вес в кг
    height = db.Column(db.Float, default=170.0)  # рост в см
    age = db.Column(db.Integer, default=25)  # возраст
    gender = db.Column(db.String(10), default='male')  # male/female

    # Объёмы мышц (в см)
    chest_circumference = db.Column(db.Float, default=0)  # грудь
    waist_circumference = db.Column(db.Float, default=0)  # талия
    hips_circumference = db.Column(db.Float, default=0)  # бёдра
    biceps_circumference = db.Column(db.Float, default=0)  # бицепс
    forearm_circumference = db.Column(db.Float, default=0)  # предплечье
    thigh_circumference = db.Column(db.Float, default=0)  # бедро
    calf_circumference = db.Column(db.Float, default=0)  # икра
    neck_circumference = db.Column(db.Float, default=0)  # шея

    # История измерений (JSON)
    measurements_history = db.Column(db.JSON, default=list)  # [{"date": "2024-01-01", "weight": 70, "biceps": 35, ...}]

    # Связи
    role = relationship('Role', back_populates='users')
    workout_templates = relationship('WorkoutTemplate', back_populates='user', cascade='all, delete-orphan')
    workout_sessions = relationship('WorkoutSession', back_populates='user', cascade='all, delete-orphan')
    schedules = db.relationship('WorkoutSchedule', back_populates='user', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<User {self.username}>'
    
    @property
    def bmi(self):
        """Индекс массы тела"""
        if self.height and self.weight:
            height_m = self.height / 100
            return round(self.weight / (height_m ** 2), 1)
        return 0
    
# Группы тренируемых мышц
class MuscleGroup(db.Model):
    __tablename__ = 'muscle_groups'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True)
    display_name = db.Column(db.String(50))

# Подгркппа тренируемых мышц
class MuscleSubgroup(db.Model):
    __tablename__ = 'muscle_subgroups'
    id = db.Column(db.Integer, primary_key=True)
    muscle_group_id = db.Column(db.Integer, db.ForeignKey('muscle_groups.id'))  # ссылается на muscle_groups
    name = db.Column(db.String(50))
    display_name = db.Column(db.String(50))

# Упражнение (глобальная база)
class Exercise(db.Model):
    __tablename__ = 'exercises'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)  # unique=True запрещает дубликаты
    exercise_type = db.Column(db.String(20), nullable=False)  # 'strength', 'cardio', 'bodyweight'
    description = db.Column(db.Text)
    
    muscle_group_id = db.Column(db.Integer, db.ForeignKey('muscle_groups.id'), nullable=True)
    muscle_subgroup_id = db.Column(db.Integer, db.ForeignKey('muscle_subgroups.id'), nullable=True)
    
    # Кто добавил упражнение
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Связи
    created_by = relationship('User', foreign_keys=[created_by_id])
    template_exercises = relationship('TemplateExercise', back_populates='exercise')
    muscle_group = relationship('MuscleGroup')
    muscle_subgroup = relationship('MuscleSubgroup')
    
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
    schedules = db.relationship('WorkoutSchedule', back_populates='template', cascade='all, delete-orphan')#исправил db.relationship на relationship
    
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
    schedule_id = db.Column(db.Integer, db.ForeignKey('workout_schedules.id'), nullable=True)
    template_id = db.Column(db.Integer, db.ForeignKey('workout_templates.id'), nullable=True)
    date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    status = db.Column(db.String(20), default='completed')  # completed, skipped
    
    # Общая оценка выполнения
    completion_percent = db.Column(db.Float, default=0.0)
    total_tonnage = db.Column(db.Float, default=0.0)  # общий тоннаж тренировки
    
    # Связи
    user = relationship('User', back_populates='workout_sessions')
    schedule = relationship('WorkoutSchedule', back_populates='session')
    template = relationship('WorkoutTemplate', back_populates='workout_sessions')  # уже есть
    set_logs = relationship('SetLog', back_populates='session', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<WorkoutSession {self.date} completion={self.completion_percent}%>'

# Лог каждого подхода (или кардио-сегмента)
class SetLog(db.Model):
    __tablename__ = 'set_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('workout_sessions.id'), nullable=False)
    exercise_id = db.Column(db.Integer, db.ForeignKey('exercises.id'), nullable=False)
    template_exercise_id = db.Column(db.Integer, db.ForeignKey('template_exercises.id'), nullable=True)
    set_number = db.Column(db.Integer, nullable=False)
    
    # Плановые значения
    planned_reps = db.Column(db.Integer, nullable=False)  # исправлено с planned_reqs
    planned_weight = db.Column(db.Float, nullable=False)
    
    # Фактические значения
    actual_reps = db.Column(db.Integer)
    actual_weight = db.Column(db.Float)
    
    # Процент выполнения подхода (по тоннажу)
    completion_percent = db.Column(db.Float, default=0.0)
    
    # Связи
    session = relationship('WorkoutSession', back_populates='set_logs')
    exercise = relationship('Exercise')
    template_exercise = relationship('TemplateExercise', back_populates='set_logs')
    
    def calculate_completion(self):
        """Расчёт процента выполнения по тоннажу (ограничение 100%)"""
        if self.actual_reps and self.actual_weight:
            planned_volume = self.planned_reps * self.planned_weight
            actual_volume = self.actual_reps * self.actual_weight
            if planned_volume > 0:
                self.completion_percent = min(100, (actual_volume / planned_volume) * 100)
            else:
                self.completion_percent = 0
        else:
            self.completion_percent = 0
        return self.completion_percent
    
    def __repr__(self):
        return f'<SetLog exercise={self.exercise_id} set={self.set_number} completion={self.completion_percent}%>'

# График тренировок
class WorkoutSchedule(db.Model):
    __tablename__ = 'workout_schedules'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey('workout_templates.id'), nullable=False)
    
    scheduled_date = db.Column(db.Date, nullable=False)
    order_index = db.Column(db.Integer, default=0)
    
    status = db.Column(db.String(20), default='planned')  # planned, completed, skipped, postponed
    
    #Плановые параметры (хранятся в JSON)
    planned_data = db.Column(db.JSON)  # {"exercise_id": {"sets": 3, "reps": 10, "weight": 50}}

    # Для повторяющихся программ (в будущем)
    is_recurring = db.Column(db.Boolean, default=False)
    recurring_rule = db.Column(db.String(50), nullable=True)
    
    # Связи
    user = db.relationship('User', back_populates='schedules')
    template = db.relationship('WorkoutTemplate', back_populates='schedules')
    session = relationship('WorkoutSession', back_populates='schedule', uselist=False)
    
    def __repr__(self):
        return f'<WorkoutSchedule {self.scheduled_date} - {self.template.name}>'
    
