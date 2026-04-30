from app import create_app, db
from app.models import MuscleGroup, MuscleSubgroup

app = create_app()
with app.app_context():
    # Добавляем группы мышц
    groups = {
        'chest': 'Грудные',
        'shoulders': 'Плечи',
        'arms': 'Руки',
        'back': 'Спина',
        'legs': 'Ноги',
        'core': 'Кор/Пресс'
    }
    
    for name, display in groups.items():
        if not MuscleGroup.query.filter_by(name=name).first():
            db.session.add(MuscleGroup(name=name, display_name=display))
    
    db.session.commit()
    
    # Добавляем уточнения для груди
    chest = MuscleGroup.query.filter_by(name='chest').first()
    if chest:
        subgroups_chest = [
            ('upper_chest', 'Верхняя часть'),
            ('middle_chest', 'Средняя часть'),
            ('lower_chest', 'Нижняя часть')
        ]
        for name, display in subgroups_chest:
            if not MuscleSubgroup.query.filter_by(name=name).first():
                db.session.add(MuscleSubgroup(muscle_group_id=chest.id, name=name, display_name=display))
    
    shoulders = MuscleGroup.query.filter_by(name='shoulders').first()
    if shoulders:
        subgroups_shoulders = [
            ('upper_shoulders', 'Передний пучок'),
            ('middle_shoulders', 'Средняя часть'),
            ('lower_shoulders', 'Задний пучок')
        ]
        for name, display in subgroups_shoulders:
            if not MuscleSubgroup.query.filter_by(name=name).first():
                db.session.add(MuscleSubgroup(muscle_group_id=shoulders.id, name=name, display_name=display))
    
    arms = MuscleGroup.query.filter_by(name='arms').first()
    if arms:
        subgroups_arms = [
            ('upper_arms', 'Бицепс'),
            ('middle_arms', 'Трицепс'),
            ('lower_arms', 'Кисти')
        ]
        for name, display in subgroups_arms:
            if not MuscleSubgroup.query.filter_by(name=name).first():
                db.session.add(MuscleSubgroup(muscle_group_id=arms.id, name=name, display_name=display))

    back = MuscleGroup.query.filter_by(name='back').first()
    if back:
        subgroups_back = [
            ('upper_back', 'Бицепс'),
            ('middle_back', 'Трицепс'),
            ('lower_back', 'Кисти')
        ]
        for name, display in subgroups_back:
            if not MuscleSubgroup.query.filter_by(name=name).first():
                db.session.add(MuscleSubgroup(muscle_group_id=back.id, name=name, display_name=display))
    
    # Для ног
    legs = MuscleGroup.query.filter_by(name='legs').first()
    if legs:
        subgroups_legs = [
            ('quads', 'Квадрицепсы'),
            ('hamstrings', 'Бицепс бедра'),
            ('calves', 'Икроножные'),
            ('glutes', 'Ягодичные')
        ]
        for name, display in subgroups_legs:
            if not MuscleSubgroup.query.filter_by(name=name).first():
                db.session.add(MuscleSubgroup(muscle_group_id=legs.id, name=name, display_name=display))

    core = MuscleGroup.query.filter_by(name='core').first()
    if core:
        subgroups_core = [
            ('press', 'Пресс'),
            ('muscl_core', 'Косые мышцы')
        ]
        for name, display in subgroups_core:
            if not MuscleSubgroup.query.filter_by(name=name).first():
                db.session.add(MuscleSubgroup(muscle_group_id=core.id, name=name, display_name=display))
    
    db.session.commit()
    print('Группы мышц и уточнения добавлены')