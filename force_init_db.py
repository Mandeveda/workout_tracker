import os
import sys

# 1. Указываем АБСОЛЮТНЫЙ путь к файлу базы данных
# Убедитесь, что путь правильный! Это ваша домашняя директория на сервере.
DB_ABSOLUTE_PATH = '/home/k/kandybd9/tracker-workout.ru/instance/workout.db'

# 2. Убеждаемся, что папка для БД существует
db_dir = os.path.dirname(DB_ABSOLUTE_PATH)
os.makedirs(db_dir, exist_ok=True)
print(f"Папка для БД: {db_dir}")

# 3. ПЕРЕопределяем переменную окружения прямо перед импортом приложения
#    (это перекроет любые настройки из .env)
os.environ['DATABASE_URL'] = f'sqlite:///{DB_ABSOLUTE_PATH}'

# 4. Теперь импортируем и запускаем приложение
from app import create_app, db
from app.models import Role, MuscleGroup, MuscleSubgroup

app = create_app()

# 5. Создаём все таблицы
with app.app_context():
    print("Создаём таблицы...")
    db.create_all()
    print("✅ Таблицы успешно созданы!")

    # 6. Проверяем, пустая ли база, и добавляем начальные данные
    if Role.query.count() == 0:
        print("Добавляем роли...")
        roles = [
            Role(id=1, name='admin', description='Полный доступ'),
            Role(id=2, name='user', description='Обычный пользователь'),
            Role(id=3, name='expert', description='Может добавлять упражнения')
        ]
        db.session.add_all(roles)
        db.session.commit()
        print("  - Роли добавлены.")

    if MuscleGroup.query.count() == 0:
        print("Добавляем группы мышц...")
        groups = {
            'chest': 'Грудные',
            'shoulders': 'Плечи',
            'arms': 'Руки',
            'back': 'Спина',
            'legs': 'Ноги',
            'core': 'Кор/Пресс'
        }
        for name, display in groups.items():
            db.session.add(MuscleGroup(name=name, display_name=display))
        db.session.commit()
        print("  - Группы мышц добавлены.")
        
    print("✅ Инициализация базы данных завершена!")