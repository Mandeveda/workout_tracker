from app import db, login_manager
from flask import current_app
from flask_login import UserMixin
import hashlib
import hmac
from datetime import datetime, timedelta
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import relationship
from math import log10

EMAIL_CONFIRM_DAYS = 30   # сколько дней даётся на подтверждение почты
# Дробные числа: в SQLite FLOAT и так 8-байтный, а в MySQL FLOAT — 4 байта (~7 цифр, 72.3 → 72.30000305),
# поэтому там — DOUBLE
Real = db.Float().with_variant(mysql.DOUBLE(asdecimal=False), 'mysql', 'mariadb')

LAST_SEEN_STEP = timedelta(minutes=5)   # как часто обновлять отметку «был на сайте»

# Загрузка пользователя для Flask-Login
@login_manager.user_loader
def load_user(user_id):
    """Загрузка пользователя по идентификатору из сессии вида "id:отпечаток" (см. User.get_id)"""
    id_part, _, fingerprint = str(user_id).partition(':')
    if not id_part.isdigit() or not fingerprint:
        return None  # старый формат или подделка — считаем, что вход не выполнен
    
    user = db.session.get(User, int(id_part))
    if user is None or user.is_blocked:
        return None
    if not hmac.compare_digest(user.password_fingerprint(), fingerprint):
        return None  # пароль сменили после входа
    return user

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
    password_hash = db.Column(db.String(256))  # хэш пароля (scrypt у Werkzeug — 162 символа)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_blocked = db.Column(db.Boolean, default=False)

    # Подтверждение почты: дата подтверждения (None — не подтверждена), срок на подтверждение
    # и новый адрес, который ждёт подтверждения (смена почты). Пока новый не подтверждён,
    # действует старый — опечатка в новом адресе не лишает доступа к аккаунту.
    email_confirmed_at = db.Column(db.DateTime, nullable=True)
    email_confirm_deadline = db.Column(db.DateTime, nullable=True,
                                       default=lambda: datetime.utcnow() + timedelta(days=EMAIL_CONFIRM_DAYS))
    pending_email = db.Column(db.String(120), nullable=True)
    # Когда пользователь последний раз открывал сайт (обновляется не чаще LAST_SEEN_STEP)
    last_seen_at = db.Column(db.DateTime, nullable=True)
    # Письма о заявках тренеру и ответах на них (уведомления на сайте приходят всегда)
    email_notifications = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    
    # Внешний ключ на роль (одна роль у пользователя)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False, default=2)  # 2 = обычный пользователь по умолчанию
    
    # Антропометрические данные
    weight = db.Column(Real, default=70.0)  # вес в кг
    height = db.Column(Real, default=170.0)  # рост в см
    age = db.Column(db.Integer, default=25)  # возраст
    gender = db.Column(db.String(10), default='male')  # male/female

    # Объёмы мышц (в см)
    chest_circumference = db.Column(Real, default=0)  # грудь
    waist_circumference = db.Column(Real, default=0)  # талия
    hips_circumference = db.Column(Real, default=0)  # бёдра
    biceps_circumference = db.Column(Real, default=0)  # бицепс
    forearm_circumference = db.Column(Real, default=0)  # предплечье
    thigh_circumference = db.Column(Real, default=0)  # бедро
    calf_circumference = db.Column(Real, default=0)  # икра
    neck_circumference = db.Column(Real, default=0)  # шея

    # История измерений (JSON)
    measurements_history = db.Column(db.JSON, default=list)  # [{"date": "2024-01-01", "weight": 70, "biceps": 35, ...}]

    # Связи
    role = relationship('Role', back_populates='users')
    workout_templates = relationship('WorkoutTemplate', back_populates='user', cascade='all, delete-orphan',
                                     foreign_keys='WorkoutTemplate.user_id')
    workout_sessions = relationship('WorkoutSession', back_populates='user', cascade='all, delete-orphan')
    schedules = db.relationship('WorkoutSchedule', back_populates='user', cascade='all, delete-orphan',
                                foreign_keys='WorkoutSchedule.user_id')

    @property
    def email_confirmed(self):
        return self.email_confirmed_at is not None

    def email_confirm_days_left(self):
        """Сколько полных дней осталось на подтверждение почты (0 — сегодня последний день или срок вышел)"""
        if self.email_confirmed or not self.email_confirm_deadline:
            return None
        from app.timeutil import utcnow
        return max(0, (self.email_confirm_deadline - utcnow()).days)

    def email_confirm_overdue(self):
        """Срок подтверждения почты истёк, а почта так и не подтверждена"""
        if self.email_confirmed or not self.email_confirm_deadline:
            return False
        from app.timeutil import utcnow
        return utcnow() > self.email_confirm_deadline

    def password_fingerprint(self):
        """Короткий отпечаток текущего пароля (HMAC от хеша, сам хеш не раскрывается)"""
        key = current_app.config['SECRET_KEY'].encode()
        return hmac.new(key, (self.password_hash or '').encode(), hashlib.sha256).hexdigest()[:16]
    
    def get_id(self):
        """Идентификатор для сессии и cookie «запомнить меня».
        
        Включает отпечаток пароля: после смены пароля все старые входы перестают действовать.
        """
        return f'{self.id}:{self.password_fingerprint()}'
    
    @property
    def is_active(self):
        """Заблокированный пользователь считается неактивным (Flask-Login не даст войти)"""
        return not self.is_blocked
    
    def can_edit(self, resource):
        """Проверка, может ли пользователь редактировать ресурс (упражнение, шаблон и т.д.)"""
        if not self.is_authenticated:
            return False
        if self.role.name == 'admin':
            return True
        # Проверяем, есть ли у ресурса атрибут user_id или created_by_id
        if hasattr(resource, 'user_id'):
            return resource.user_id == self.id
        if hasattr(resource, 'created_by_id'):
            return resource.created_by_id == self.id
        return False
    
    def can_delete(self, resource):
        """Проверка, может ли пользователь удалить ресурс"""
        return self.can_edit(resource)

    def __repr__(self):
        return f'<User {self.username}>'
    
    @property
    def bmi(self):
        """Индекс массы тела"""
        if self.height and self.weight:
            height_m = self.height / 100
            return round(self.weight / (height_m ** 2), 1)
        return 0
    
    @property
    def body_fat_percentage(self):
        """Процент жира по методике ВМС США (только при наличии замеров)"""
        # Проверяем наличие всех необходимых данных
        if not (self.height and self.weight and self.neck_circumference and self.waist_circumference):
            return None
        
        # Для женщин нужен ещё обхват бёдер
        if self.gender == 'female' and not self.hips_circumference:
            return None
        
        try:
            if self.gender == 'male':
                # Формула для мужчин (размеры в см)
                result = 495 / (
                    1.0324 - 
                    0.19077 * log10(self.waist_circumference - self.neck_circumference) + 
                    0.15456 * log10(self.height)
                ) - 450
            else:  # female
                result = 495 / (
                    1.29579 - 
                    0.35004 * log10(
                        self.waist_circumference + self.hips_circumference - self.neck_circumference
                    ) + 
                    0.22100 * log10(self.height)
                ) - 450
            
            # Ограничиваем результат разумными пределами
            if result < 5:
                result = 5
            elif result > 50:
                result = 50
                
            return round(result, 1)
        except (ValueError, ZeroDivisionError):
            return None
    
    @property
    def ffmi(self):
        """Индекс мышечной массы (FFMI)"""
        body_fat = self.body_fat_percentage
        if body_fat is None or body_fat <= 0 or body_fat >= 100:
            return None
        
        if self.height and self.weight:
            height_m = self.height / 100
            # Безжировая масса (кг) = вес * (100 - %жира) / 100
            lean_mass = self.weight * (100 - body_fat) / 100
            # FFMI = безжировая масса / рост²
            ffmi_value = lean_mass / (height_m ** 2)
            return round(ffmi_value, 1)
        return None
    
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
    
    media_type = db.Column(db.String(10), default='none')  # 'image', 'gif', 'video', 'youtube', 'none'
    media_url = db.Column(db.String(500), nullable=True)   # URL изображения, гифки или видео
    youtube_id = db.Column(db.String(20), nullable=True)   # ID видео с YouTube (например, dQw4w9WgXcQ)
    thumbnail_url = db.Column(db.String(500), nullable=True) # миниатюра для видео
    
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
    is_active = db.Column(db.Boolean, default=True) 
    # Тренер, который назначил шаблон (это копия его шаблона у подопечного); пусто — свой шаблон
    assigned_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Для привязки к дате/дню недели
    scheduled_date = db.Column(db.Date, nullable=True)  # если привязано к конкретной дате
    scheduled_weekday = db.Column(db.Integer, nullable=True)  # 0-6 (пн=0, вс=6)
    
    # Связи
    user = relationship('User', back_populates='workout_templates', foreign_keys=[user_id])
    assigned_by = relationship('User', foreign_keys=[assigned_by_id])
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
    planned_weight = db.Column(Real)  # в кг
    
    # Параметры для кардио
    planned_duration = db.Column(db.Integer)  # в минутах
    planned_distance = db.Column(Real)  # в км
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
    # Название шаблона на момент тренировки: остаётся в истории, если шаблон удалят
    template_name = db.Column(db.String(100), nullable=True)
    date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    status = db.Column(db.String(20), default='in_progress')  # in_progress, completed
    
    # Общая оценка выполнения
    completion_percent = db.Column(Real, default=0.0)
    total_tonnage = db.Column(Real, default=0.0)  # общий тоннаж тренировки
    is_completed = db.Column(db.Boolean, default=False)
    
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
    planned_weight = db.Column(Real, nullable=False)
    
    # Фактические значения
    actual_reps = db.Column(db.Integer)
    actual_weight = db.Column(Real)
    
    # Процент выполнения подхода (по тоннажу)
    completion_percent = db.Column(Real, default=0.0)
    
    # Связи
    session = relationship('WorkoutSession', back_populates='set_logs')
    exercise = relationship('Exercise')
    template_exercise = relationship('TemplateExercise', back_populates='set_logs')
    
    def calculate_completion(self, user_weight=None):
        """Расчёт процента выполнения по тоннажу (ограничение 100%)
        
        Для упражнений с собственным весом использует вес пользователя
        """
        # У только что созданного подхода связь exercise ещё не загружена
        # (заполнен только exercise_id), поэтому при необходимости берём упражнение из БД
        exercise = self.exercise
        if exercise is None and self.exercise_id:
            exercise = db.session.get(Exercise, self.exercise_id)
        exercise_type = exercise.exercise_type if exercise else 'strength'
        
        # Для кардио
        if exercise_type == 'cardio':
            # Кардио: сравниваем длительность и дистанцию
            if self.actual_reps and self.planned_reps:
                planned_volume = self.planned_reps  # длительность в минутах
                actual_volume = self.actual_reps
                if planned_volume > 0:
                    self.completion_percent = min(100, (actual_volume / planned_volume) * 100)
                else:
                    self.completion_percent = 0
            else:
                self.completion_percent = 0
            return self.completion_percent
        
        # Для bodyweight (собственный вес)
        if exercise_type == 'bodyweight':
            if self.actual_reps and self.planned_reps > 0:
                # Используем вес пользователя если передан, иначе 70 (средний вес)
                weight = user_weight if user_weight and user_weight > 0 else 70
                
                planned_volume = self.planned_reps * weight
                actual_volume = self.actual_reps * weight
                
                if planned_volume > 0:
                    self.completion_percent = min(100, (actual_volume / planned_volume) * 100)
                else:
                    self.completion_percent = 0
            else:
                self.completion_percent = 0
            return self.completion_percent
        
        # Для силовых (с весом)
        if self.actual_reps and self.actual_weight is not None and self.planned_reps > 0:
            planned_volume = self.planned_reps * (self.planned_weight or 0)
            actual_volume = self.actual_reps * (self.actual_weight or 0)
            
            if planned_volume > 0:
                self.completion_percent = min(100, (actual_volume / planned_volume) * 100)
            else:
                # План без веса (0 кг) — сравниваем только повторения
                self.completion_percent = min(100, (self.actual_reps / self.planned_reps) * 100)
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
    # Пусто у проведённых тренировок удалённого шаблона (план подходов остаётся в planned_data)
    template_id = db.Column(db.Integer, db.ForeignKey('workout_templates.id'), nullable=True)
    
    scheduled_date = db.Column(db.Date, nullable=False)
    order_index = db.Column(db.Integer, default=0)
    
    status = db.Column(db.String(20), default='planned')  # planned, completed, skipped, postponed
    
    #Плановые параметры (хранятся в JSON)
    planned_data = db.Column(db.JSON)  # {"exercise_id": {"sets": 3, "reps": 10, "weight": 50}}

    # Для повторяющихся программ (в будущем)
    is_recurring = db.Column(db.Boolean, default=False)
    recurring_rule = db.Column(db.String(50), nullable=True)
    # Тренер, который поставил этот день в расписание; пусто — пользователь сам
    assigned_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Связи
    user = db.relationship('User', back_populates='schedules', foreign_keys=[user_id])
    assigned_by = db.relationship('User', foreign_keys=[assigned_by_id])
    template = db.relationship('WorkoutTemplate', back_populates='schedules')
    session = relationship('WorkoutSession', back_populates='schedule', uselist=False)
    
    def __repr__(self):
        return f'<WorkoutSchedule {self.scheduled_date} - {self.template.name if self.template else self.template_id}>'
    
class PasswordResetToken(db.Model):
    __tablename__ = 'password_reset_tokens'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token = db.Column(db.String(100), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    used = db.Column(db.Boolean, default=False)
    
    user = relationship('User', backref='reset_tokens')
    
    def __repr__(self):
        return f'<PasswordResetToken user={self.user_id} expires={self.expires_at}>'
    
    def is_expired(self):
        """Проверка, истёк ли токен"""
        return datetime.utcnow() > self.expires_at
    
    def is_valid(self):
        """Проверка, действителен ли токен"""
        return not self.used and not self.is_expired()


# ---------- Тренеры (ROADMAP D) ----------

COACH_STATUSES = ('pending', 'approved', 'rejected', 'revoked')   # на проверке, одобрен, отклонён, статус снят
LINK_STATUSES = ('requested', 'active', 'declined', 'ended')      # заявка, подопечный, заявка отклонена, связь разорвана
REVIEW_MIN_SESSIONS = 3      # столько тренировок по назначению тренера нужно провести, чтобы оставить отзыв
RATING_MIN_REVIEWS = 3       # с какого числа отзывов показывается рейтинг

coach_specializations = db.Table(
    'coach_specializations',
    db.Column('coach_profile_id', db.Integer, db.ForeignKey('coach_profiles.id'), primary_key=True),
    db.Column('specialization_id', db.Integer, db.ForeignKey('specializations.id'), primary_key=True),
)


class Specialization(db.Model):
    """Направление работы тренера; список ведёт админ"""
    __tablename__ = 'specializations'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), unique=True, nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default='1')   # скрытые не предлагаются в анкете

    def __repr__(self):
        return f'<Specialization {self.name}>'


class CoachProfile(db.Model):
    """Анкета тренера. Тренер — не роль, а дополнительный статус любого пользователя"""
    __tablename__ = 'coach_profiles'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')
    bio = db.Column(db.Text, nullable=True)                       # «о себе», достижения
    experience_years = db.Column(db.Integer, nullable=True)
    city = db.Column(db.String(80), nullable=True)
    works_online = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    works_offline = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    contacts = db.Column(db.String(300), nullable=True)           # видны только подопечным
    photo = db.Column(db.String(100), nullable=True)              # имя файла в папке фото тренеров
    max_clients = db.Column(db.Integer, nullable=True)            # пусто — без ограничения
    accepting = db.Column(db.Boolean, nullable=False, default=True, server_default='1')   # набор открыт
    admin_note = db.Column(db.String(300), nullable=True)         # причина отказа / снятия статуса
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.utcnow)
    approved_at = db.Column(db.DateTime, nullable=True)

    user = relationship('User', backref=db.backref('coach_profile', uselist=False))
    specializations = relationship('Specialization', secondary=coach_specializations,
                                   order_by='Specialization.sort_order')

    @property
    def is_approved(self):
        return self.status == 'approved'

    def __repr__(self):
        return f'<CoachProfile user={self.user_id} {self.status}>'


class CoachLink(db.Model):
    """Связь тренер ↔ подопечный: от заявки до разрыва (история сохраняется)"""
    __tablename__ = 'coach_links'

    id = db.Column(db.Integer, primary_key=True)
    coach_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='requested')
    message = db.Column(db.String(500), nullable=True)            # сообщение в заявке
    share_measurements = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    answered_at = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)
    ended_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    coach = relationship('User', foreign_keys=[coach_id])
    client = relationship('User', foreign_keys=[client_id])

    @property
    def is_active(self):
        return self.status == 'active'

    def __repr__(self):
        return f'<CoachLink coach={self.coach_id} client={self.client_id} {self.status}>'


class SessionComment(db.Model):
    """Комментарий тренера к проведённой тренировке подопечного"""
    __tablename__ = 'session_comments'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('workout_sessions.id'), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.utcnow)

    session = relationship('WorkoutSession', backref=db.backref('comments', order_by='SessionComment.created_at'))
    author = relationship('User')


class CoachReview(db.Model):
    """Отзыв подопечного о тренере: один на пару, можно исправить"""
    __tablename__ = 'coach_reviews'
    __table_args__ = (db.UniqueConstraint('coach_id', 'author_id', name='uq_coach_review_author'),)

    id = db.Column(db.Integer, primary_key=True)
    coach_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)                # 1–5
    text = db.Column(db.Text, nullable=True)
    reply = db.Column(db.Text, nullable=True)                     # ответ тренера (один)
    replied_at = db.Column(db.DateTime, nullable=True)
    reported_at = db.Column(db.DateTime, nullable=True)           # тренер пожаловался
    is_hidden = db.Column(db.Boolean, nullable=False, default=False, server_default='0')   # скрыт админом
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.utcnow)

    coach = relationship('User', foreign_keys=[coach_id])
    author = relationship('User', foreign_keys=[author_id])


class Notification(db.Model):
    """Уведомление на сайте (колокольчик)"""
    __tablename__ = 'notifications'
    __table_args__ = (db.Index('ix_notifications_user_read', 'user_id', 'read_at'),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    kind = db.Column(db.String(30), nullable=False)               # coach_request, request_answer, …
    text = db.Column(db.String(300), nullable=False)
    url = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    read_at = db.Column(db.DateTime, nullable=True)
