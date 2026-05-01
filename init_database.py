import json
from app import create_app, db
from app.models import Role, MuscleGroup, MuscleSubgroup, User
from werkzeug.security import generate_password_hash

def load_data_from_json(filename):
    with open(filename, 'r', encoding='utf-8') as file:
        return json.load(file)

def init_roles(data):
    print("Инициализация ролей...")
    for role_data in data['roles']:
        if not Role.query.filter_by(name=role_data['name']).first():
            role = Role(
                id=role_data['id'],
                name=role_data['name'],
                description=role_data['description']
            )
            db.session.add(role)
    db.session.commit()
    print("Роли добавлены.")

def init_muscle_groups(data):
    print("Инициализация групп мышц...")
    for group_data in data['muscle_groups']:
        if not MuscleGroup.query.filter_by(name=group_data['name']).first():
            group = MuscleGroup(
                name=group_data['name'],
                display_name=group_data['display_name']
            )
            db.session.add(group)
    db.session.commit()
    print("Группы мышц добавлены.")

def init_muscle_subgroups(data):
    print("Инициализация подгрупп мышц...")


    # Словарь соответствия: подгруппа → группа мышц
    SUBGROUP_TO_GROUP = {
        'upper_chest': 'chest',
        'middle_chest': 'chest',
        'lower_chest': 'chest',
        'upper_shoulders': 'shoulders',
        'middle_shoulders': 'shoulders',
        'lower_shoulders': 'shoulders',
        'upper_arms': 'arms',
        'middle_arms': 'arms',
        'lower_arms': 'arms',
        'upper_back': 'back',
        'middle_back': 'back',
        'lower_back': 'back',
        'quads': 'legs',
        'hamstrings': 'legs',
        'calves': 'legs',
        'glutes': 'legs',
        'press': 'core',
        'muscl_core': 'core'
    }

    for subgroup_data in data['muscle_subgroups']:
        # Получаем название группы мышц из словаря соответствия
        group_name = SUBGROUP_TO_GROUP.get(subgroup_data['name'])

        if not group_name:
            print(f"Предупреждение: для подгруппы '{subgroup_data['name']}' не найдено соответствие группы мышц. Пропускаем.")
            continue

        # Находим группу мышц по имени
        muscle_group = MuscleGroup.query.filter_by(name=group_name).first()

        if muscle_group:
            # Проверяем, не существует ли уже такая подгруппа
            if not MuscleSubgroup.query.filter_by(
                name=subgroup_data['name'],
                muscle_group_id=muscle_group.id
            ).first():
                subgroup = MuscleSubgroup(
                    muscle_group_id=muscle_group.id,
            name=subgroup_data['name'],
            display_name=subgroup_data['display_name']
                )
                db.session.add(subgroup)
        else:
            print(f"Ошибка: группа мышц '{group_name}' не найдена в БД для подгруппы '{subgroup_data['name']}'. Пропускаем.")

    db.session.commit()
    print("Подгруппы мышц добавлены.")

def init_users(data):
    print("Инициализация пользователей...")
    for user_data in data['users']:
        if not User.query.filter_by(username=user_data['username']).first():
            user = User(
                username=user_data['username'],
                email=user_data['email'],
                password_hash=generate_password_hash(user_data['password']),
                role_id=user_data['role_id']
            )
            db.session.add(user)
    db.session.commit()
    print("Пользователи добавлены.")

def main():
    app = create_app()
    with app.app_context():
        data = load_data_from_json('data_for_init.json')
        init_roles(data)
        init_muscle_groups(data)
        init_muscle_subgroups(data)
        init_users(data)
        print("Инициализация базы данных завершена!")

if __name__ == '__main__':
    main()
