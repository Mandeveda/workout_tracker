from flask import render_template, redirect, url_for, flash, request, Blueprint
from flask_login import login_required, current_user
from datetime import datetime
from app import db
from app.forms import ProfileForm, MeasurementForm
from app.models import User
import json

bp = Blueprint('profile', __name__, url_prefix='/profile')

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
        
        if form.username.data != current_user.username:
            existing_user = User.query.filter_by(username=form.username.data).first()
            if existing_user:
                flash('Это имя пользователя уже занято', 'danger')
                return render_template('profile/edit.html', form=form, user=current_user)
            current_user.username = form.username.data

        current_user.weight = form.weight.data
        current_user.height = form.height.data
        current_user.age = form.age.data
        current_user.gender = form.gender.data
        
        current_user.chest_circumference = form.chest_circumference.data
        current_user.waist_circumference = form.waist_circumference.data
        current_user.hips_circumference = form.hips_circumference.data
        current_user.biceps_circumference = form.biceps_circumference.data
        current_user.forearm_circumference = form.forearm_circumference.data
        current_user.thigh_circumference = form.thigh_circumference.data
        current_user.calf_circumference = form.calf_circumference.data
        current_user.neck_circumference = form.neck_circumference.data
        
        db.session.commit()
        flash('Профиль успешно обновлён!', 'success')
        return redirect(url_for('profile.index'))
    
    return render_template('profile/edit.html', form=form, user=current_user)

@bp.route('/add_measurement', methods=['POST'])
@login_required
def add_measurement():
    """Добавление нового измерения в историю"""
    form = MeasurementForm()
    
    if form.validate_on_submit():
        measurement = {
            'date': datetime.utcnow().isoformat(),
            'weight': form.weight.data,
            'chest': form.chest_circumference.data,
            'waist': form.waist_circumference.data,
            'hips': form.hips_circumference.data,
            'biceps': form.biceps_circumference.data
        }
        
        if not current_user.measurements_history:
            current_user.measurements_history = []
        
        current_user.measurements_history.append(measurement)
        
        # Обновляем текущие значения
        current_user.weight = form.weight.data
        current_user.chest_circumference = form.chest_circumference.data
        current_user.waist_circumference = form.waist_circumference.data
        current_user.hips_circumference = form.hips_circumference.data
        current_user.biceps_circumference = form.biceps_circumference.data
        
        db.session.commit()
        flash('Измерение добавлено!', 'success')
    
    return redirect(url_for('profile.index'))

@bp.route('/measurements_data')
@login_required
def measurements_data():
    """Данные для графика измерений (JSON)"""
    from flask import jsonify
    
    history = current_user.measurements_history or []
    
    # Сортируем по дате
    history.sort(key=lambda x: x['date'])
    
    return jsonify({
        'dates': [m['date'][:10] for m in history],
        'weights': [m.get('weight', 0) for m in history],
        'chest': [m.get('chest', 0) for m in history],
        'waist': [m.get('waist', 0) for m in history],
        'biceps': [m.get('biceps', 0) for m in history]
    })