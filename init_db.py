from app import create_app, db
from app.models import Role

app = create_app()
with app.app_context():
    # Добавляем роли если их нет
    if Role.query.count() == 0:
        roles = [
            Role(id=1, name='admin', description='Полный доступ'),
            Role(id=2, name='user', description='Обычный пользователь'),
            Role(id=3, name='expert', description='Может добавлять упражнения')
        ]
        db.session.add_all(roles)
        db.session.commit()
        print('Роли добавлены')
    else:
        print('Роли уже существуют')