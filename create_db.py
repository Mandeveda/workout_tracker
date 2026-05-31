from app import create_app, db
from app.models import *

print("Создаём приложение...")
app = create_app()
print("Приложение создано. Устанавливаем контекст...")
app.app_context().push()
print("Контекст установлен. Создаём таблицы...")
db.create_all()
print("✅ Таблицы успешно созданы!")