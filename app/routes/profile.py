from flask import render_template, redirect, url_for, flash, request, Blueprint, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from app import db
from app.models import User
from app.forms import ProfileForm
import json
import logging

bp = Blueprint('profile', __name__, url_prefix='/profile')

# Настройка логирования
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@bp.route('/')
@login_required
def index():
    """Страница профиля"""
    return render_template('profile/index.html', user=current_user)

@bp.route('/edit', methods=['GET', 'POST'])
@login_required
def edit():
    """Редактирование профиля"""
    form = ProfileForm(obj=current_user)
    
    if form.validate_on_submit():
        logger.debug("=== РЕДАКТИРОВАНИЕ ПРОФИЛЯ ===")
        
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
        
        # Создаем измерение
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
        
        # Добавляем в историю
        history_list = list(current_user.measurements_history)
        history_list.append(measurement)
        current_user.measurements_history = history_list
        
        # Сохраняем
        try:
            db.session.add(current_user)
            db.session.commit()
            logger.debug(f"✅ Сохранено измерение #{len(current_user.measurements_history)}")
            flash(f'✅ Профиль обновлен! Измерение #{len(current_user.measurements_history)} сохранено.', 'success')
        except Exception as e:
            db.session.rollback()
            logger.error(f"❌ Ошибка: {e}")
            flash(f'❌ Ошибка: {str(e)}', 'danger')
        
        return redirect(url_for('profile.index'))
    
    return render_template('profile/edit.html', form=form, user=current_user)

@bp.route('/add_measurement', methods=['POST'])
@login_required
def add_measurement():
    """Добавление нового измерения"""
    logger.debug("=== ДОБАВЛЕНИЕ ИЗМЕРЕНИЯ ===")
    
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
        
        logger.debug(f"Получены данные: вес={weight}, грудь={chest}, талия={waist}, бедра={hips}, бицепс={biceps}, предплечье={forearm}, бедро={thigh}, икра={calf}, шея={neck}")
        
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
            logger.debug("Инициализирована новая история")
        
        # ✅ ВАЖНО: Создаем новый список, а не изменяем существующий
        history_list = list(current_user.measurements_history)
        history_list.append(measurement)
        current_user.measurements_history = history_list
        
        logger.debug(f"История после добавления: {len(current_user.measurements_history)} измерений")
        
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
        logger.debug("✅ Изменения сохранены в БД")
        
        # ✅ ПРОВЕРЯЕМ: перезагружаем объект
        db.session.refresh(current_user)
        final_count = len(current_user.measurements_history) if current_user.measurements_history else 0
        logger.debug(f"После сохранения в истории: {final_count} измерений")
        
        flash(f'✅ Измерение добавлено! Теперь в истории {final_count} записей.', 'success')
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        flash(f'❌ Ошибка: {str(e)}', 'danger')
    
    return redirect(url_for('profile.index'))

@bp.route('/measurements_data')
@login_required
def measurements_data():
    """Данные для графика"""
    logger.debug("=== ЗАПРОС ДАННЫХ ДЛЯ ГРАФИКА ===")
    
    # Принудительно обновляем объект пользователя из БД
    db.session.refresh(current_user)
    
    history = current_user.measurements_history
    
    if history is None:
        logger.debug("История = None")
        history = []
    elif isinstance(history, str):
        # Если вдруг строка, пытаемся распарсить JSON
        try:
            history = json.loads(history)
            logger.debug("Распарсили JSON строку")
        except:
            history = []
            logger.debug("Не удалось распарсить JSON")
    
    logger.debug(f"Тип history: {type(history)}")
    logger.debug(f"Количество измерений: {len(history) if history else 0}")
    
    if history and len(history) > 0:
        # Сортируем по дате
        history.sort(key=lambda x: x.get('date', ''))
        logger.debug(f"Первое измерение: {history[0]}")
        logger.debug(f"Последнее измерение: {history[-1]}")
    else:
        logger.debug("История пуста")
    
    # Формируем ответ
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
    
    logger.debug(f"Отправляем {len(response_data['dates'])} дат")
    
    return jsonify(response_data)