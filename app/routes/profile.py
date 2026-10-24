from flask import render_template, redirect, url_for, flash, request, Blueprint, jsonify, current_app
from flask_login import login_required, current_user, login_user
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
from app import db
from app.models import User
from app.forms import ProfileForm, ChangePasswordForm, ChangeEmailForm
from app import limiter, email_confirm
from app.routes.auth import is_safe_redirect
from sqlalchemy import func
import json

bp = Blueprint('profile', __name__, url_prefix='/profile')


# Обхваты: ключ в истории замеров, подпись, поле модели
MEASURES = [
    ('chest', 'Грудь', 'chest_circumference'),
    ('waist', 'Талия', 'waist_circumference'),
    ('hips', 'Бёдра', 'hips_circumference'),
    ('neck', 'Шея', 'neck_circumference'),
    ('biceps', 'Бицепс', 'biceps_circumference'),
    ('forearm', 'Предплечье', 'forearm_circumference'),
    ('thigh', 'Бедро', 'thigh_circumference'),
    ('calf', 'Икра', 'calf_circumference'),
]


def body_status(user):
    """Оценки ИМТ, процента жира и FFMI: (значение, подпись, тон — ok/warn/low/info)"""
    bmi = user.bmi
    if not bmi:
        bmi_s = None
    elif bmi < 18.5:
        bmi_s = (bmi, 'недостаток веса', 'warn')
    elif bmi < 25:
        bmi_s = (bmi, 'норма', 'ok')
    elif bmi < 30:
        bmi_s = (bmi, 'избыток веса', 'warn')
    else:
        bmi_s = (bmi, 'ожирение', 'low')

    fat = user.body_fat_percentage
    fat_s = None
    if fat:
        limits = (10, 20, 25) if user.gender == 'male' else (18, 28, 33)
        labels = [('атлетичный', 'info'), ('норма', 'ok'), ('выше нормы', 'warn'), ('высокий', 'low')]
        idx = sum(fat >= limit for limit in limits)
        fat_s = (fat, *labels[idx])

    ffmi = user.ffmi
    ffmi_s = None
    if ffmi:
        steps = [(18, 'ниже среднего', 'info'), (20, 'средний', 'ok'), (22, 'хороший', 'ok'), (25, 'отличный', 'ok')]
        ffmi_s = next(((ffmi, label, tone) for limit, label, tone in steps if ffmi < limit), (ffmi, 'выдающийся', 'ok'))
    return {'bmi': bmi_s, 'fat': fat_s, 'ffmi': ffmi_s}


def sorted_history(user):
    history = user.measurements_history or []
    if isinstance(history, str):
        try:
            history = json.loads(history)
        except ValueError:
            history = []
    return sorted(history, key=lambda m: m.get('date', ''))


@bp.route('/')
@login_required
def index():
    """Страница профиля"""
    history = sorted_history(current_user)
    prev = history[-2] if len(history) >= 2 else None

    def delta(key, value):
        if not prev or not prev.get(key) or not value:
            return None
        return round(value - prev[key], 1)

    measures = [{
        'key': key,
        'label': label,
        'value': getattr(current_user, attr) or 0,
        'delta': delta(key, getattr(current_user, attr) or 0),
    } for key, label, attr in MEASURES]

    return render_template('profile/index.html',
                           user=current_user,
                           status=body_status(current_user),
                           measures=measures,
                           weight_delta=delta('weight', current_user.weight),
                           history_count=len(history),
                           last_measured=datetime.fromisoformat(history[-1]['date'][:10]).strftime('%d.%m.%Y') if history else None)

@bp.route('/edit', methods=['GET', 'POST'])
@login_required
def edit():
    """Редактирование профиля"""
    form = ProfileForm(obj=current_user)
    
    if form.validate_on_submit():
        
        # Проверка уникальности username
        if form.username.data != current_user.username:
            existing_user = User.query.filter_by(username=form.username.data).first()
            if existing_user:
                flash('Это имя пользователя уже занято', 'danger')
                return render_template('profile/edit.html', form=form, user=current_user)
            current_user.username = form.username.data

        # Обновляем текущие значения
        current_user.weight = form.weight.data
        current_user.height = form.height.data
        current_user.age = form.age.data
        current_user.gender = form.gender.data
        current_user.chest_circumference = form.chest_circumference.data or 0
        current_user.waist_circumference = form.waist_circumference.data or 0
        current_user.hips_circumference = form.hips_circumference.data or 0
        current_user.biceps_circumference = form.biceps_circumference.data or 0
        current_user.forearm_circumference = form.forearm_circumference.data or 0
        current_user.thigh_circumference = form.thigh_circumference.data or 0
        current_user.calf_circumference = form.calf_circumference.data or 0
        current_user.neck_circumference = form.neck_circumference.data or 0
        
        # Инициализация истории
        if current_user.measurements_history is None:
            current_user.measurements_history = []
        
        # Замер в историю добавляем, только если изменился вес или какой-то обхват
        measurement = {
            'date': datetime.utcnow().isoformat(),
            'weight': float(current_user.weight),
            'chest': float(current_user.chest_circumference),
            'waist': float(current_user.waist_circumference),
            'hips': float(current_user.hips_circumference),
            'biceps': float(current_user.biceps_circumference),
            'forearm': float(current_user.forearm_circumference),
            'thigh': float(current_user.thigh_circumference),
            'calf': float(current_user.calf_circumference),
            'neck': float(current_user.neck_circumference)
        }
        
        history_list = list(current_user.measurements_history)
        last = sorted_history(current_user)[-1] if history_list else None
        changed = last is None or any(
            round(float(last.get(k, 0) or 0), 1) != round(v, 1) for k, v in measurement.items() if k != 'date'
        )
        if changed:
            history_list.append(measurement)
            current_user.measurements_history = history_list
        
        # Сохраняем
        try:
            db.session.add(current_user)
            db.session.commit()
            flash('Профиль сохранён.' + (' Новый замер добавлен в историю.' if changed else ''), 'success')
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Ошибка сохранения профиля (user_id=%s)', current_user.id)
            flash('Не удалось сохранить. Попробуйте ещё раз — если ошибка повторится, напишите администратору.', 'danger')
        
        return redirect(url_for('profile.index'))
    
    return render_template('profile/edit.html', form=form, user=current_user,
                           password_form=ChangePasswordForm(formdata=None), email_form=ChangeEmailForm(formdata=None))


@bp.route('/change_password', methods=['POST'])
@login_required
def change_password():
    """Смена пароля. Остальные входы пользователя завершаются, текущий — сохраняется"""
    form = ChangePasswordForm()
    if not form.validate_on_submit():
        for errors in form.errors.values():
            for error in errors:
                flash(error, 'danger')
        return redirect(url_for('profile.edit') + '#password')
    if not check_password_hash(current_user.password_hash or '', form.old_password.data):
        flash('Текущий пароль указан неверно', 'danger')
        return redirect(url_for('profile.edit') + '#password')

    current_user.password_hash = generate_password_hash(form.new_password.data)
    db.session.commit()
    # Отпечаток пароля в сессии изменился (см. User.get_id) — заново входим на этом устройстве
    login_user(current_user, remember=True)
    flash('Пароль изменён. На других устройствах нужно будет войти заново.', 'success')
    return redirect(url_for('profile.index'))

@bp.route('/change_email', methods=['POST'])
@login_required
@limiter.limit("5 per hour")
def change_email():
    """Смена почты: ссылка подтверждения уходит на новый адрес, до подтверждения действует старый"""
    form = ChangeEmailForm()
    back = url_for('profile.edit') + '#email'
    if not form.validate_on_submit():
        for errors in form.errors.values():
            for error in errors:
                flash(error, 'danger')
        return redirect(back)
    if not check_password_hash(current_user.password_hash or '', form.password.data):
        flash('Текущий пароль указан неверно', 'danger')
        return redirect(back)
    new_email = form.new_email.data
    if new_email == current_user.email.lower():
        flash('Это и так ваша текущая почта.', 'info')
        return redirect(back)
    if User.query.filter(func.lower(User.email) == new_email, User.id != current_user.id).first():
        flash('Этот адрес уже занят другим аккаунтом.', 'danger')
        return redirect(back)

    current_user.pending_email = new_email
    db.session.commit()
    try:
        email_confirm.send_confirmation(current_user, new_email)
        flash(f'Мы отправили ссылку на {new_email}. Пока вы её не подтвердите, используется прежняя почта.', 'success')
    except Exception:
        current_app.logger.exception('Не удалось отправить письмо смены почты (user_id=%s)', current_user.id)
        flash('Новый адрес сохранён, но письмо отправить не удалось — отправьте его ещё раз из напоминания вверху.', 'warning')
    return redirect(url_for('profile.index'))


@bp.route('/cancel_email_change', methods=['POST'])
@login_required
def cancel_email_change():
    current_user.pending_email = None
    db.session.commit()
    flash('Смена почты отменена.', 'info')
    back = request.form.get('next')
    return redirect(back if is_safe_redirect(back) else url_for('profile.index'))


@bp.route('/add_measurement', methods=['POST'])
@login_required
def add_measurement():
    """Добавление нового измерения"""
    
    try:
        weight = request.form.get('weight', type=float)
        
        if not weight or weight < 30 or weight > 300:
            flash('Вес должен быть от 30 до 300 кг', 'danger')
            return redirect(url_for('profile.index'))
        
        # Получаем все данные из формы
        chest = request.form.get('chest_circumference', type=float)
        waist = request.form.get('waist_circumference', type=float)
        hips = request.form.get('hips_circumference', type=float)
        biceps = request.form.get('biceps_circumference', type=float)
        forearm = request.form.get('forearm_circumference', type=float)
        thigh = request.form.get('thigh_circumference', type=float)
        calf = request.form.get('calf_circumference', type=float)
        neck = request.form.get('neck_circumference', type=float)
        
        
        # Создаем измерение
        measurement = {
            'date': datetime.utcnow().isoformat(),
            'weight': float(weight),
            'chest': float(chest) if chest else 0,
            'waist': float(waist) if waist else 0,
            'hips': float(hips) if hips else 0,
            'biceps': float(biceps) if biceps else 0,
            'forearm': float(forearm) if forearm else 0,
            'thigh': float(thigh) if thigh else 0,
            'calf': float(calf) if calf else 0,
            'neck': float(neck) if neck else 0
        }
        
        # Инициализация истории
        if current_user.measurements_history is None or current_user.measurements_history == '':
            current_user.measurements_history = []
        
        # ✅ ВАЖНО: Создаем новый список, а не изменяем существующий
        history_list = list(current_user.measurements_history)
        history_list.append(measurement)
        current_user.measurements_history = history_list
        
        
        # Обновляем текущие параметры
        current_user.weight = weight
        
        if chest is not None:
            current_user.chest_circumference = chest
        if waist is not None:
            current_user.waist_circumference = waist
        if hips is not None:
            current_user.hips_circumference = hips
        if biceps is not None:
            current_user.biceps_circumference = biceps
        if forearm is not None:
            current_user.forearm_circumference = forearm
        if thigh is not None:
            current_user.thigh_circumference = thigh
        if calf is not None:
            current_user.calf_circumference = calf
        if neck is not None:
            current_user.neck_circumference = neck
        
        # ✅ ПРИНУДИТЕЛЬНО помечаем поле как измененное
        db.session.add(current_user)
        db.session.flush()
        
        # Коммитим
        db.session.commit()
        
        # ✅ ПРОВЕРЯЕМ: перезагружаем объект
        db.session.refresh(current_user)
        final_count = len(current_user.measurements_history) if current_user.measurements_history else 0
        
        flash(f'✅ Измерение добавлено! Теперь в истории {final_count} записей.', 'success')
        
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Ошибка сохранения замера (user_id=%s)', current_user.id)
        flash('Не удалось сохранить. Попробуйте ещё раз — если ошибка повторится, напишите администратору.', 'danger')
    
    return redirect(url_for('profile.index'))

@bp.route('/measurements_data')
@login_required
def measurements_data():
    """Данные для графика замеров"""
    history = sorted_history(current_user)
    response_data = {
        'dates': [m.get('date', '')[:10] for m in history] if history else [],
        'weights': [float(m.get('weight', 0)) for m in history] if history else [],
        'chest': [float(m.get('chest', 0)) for m in history] if history else [],
        'waist': [float(m.get('waist', 0)) for m in history] if history else [],
        'hips': [float(m.get('hips', 0)) for m in history] if history else [],
        'biceps': [float(m.get('biceps', 0)) for m in history] if history else [],
        'forearm': [float(m.get('forearm', 0)) for m in history] if history else [],
        'thigh': [float(m.get('thigh', 0)) for m in history] if history else [],
        'calf': [float(m.get('calf', 0)) for m in history] if history else [],
        'neck': [float(m.get('neck', 0)) for m in history] if history else []
    }
    return jsonify(response_data)