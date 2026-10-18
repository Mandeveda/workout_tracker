"""Пересчёт процента выполнения подходов и итогов тренировок по уже сохранённым данным.

Нужен после исправлений в расчётах (план 1.2 и далее): старые записи хранят
проценты, посчитанные с ошибкой.

Запуск:
    python recalc_stats.py           # только показать, что изменится
    python recalc_stats.py --apply   # записать изменения в БД

Перед --apply на сервере сделайте копию базы (instance/workout.db).
"""
import sys

from app import create_app, db
from app.models import SetLog, WorkoutSession
from app.routes.workouts import session_totals


def recalc(apply_changes):
    changed_logs = 0

    for log in SetLog.query.all():
        old_percent = log.completion_percent or 0
        user_weight = log.session.user.weight if log.session and log.session.user else None
        new_percent = log.calculate_completion(user_weight)

        if round(old_percent, 1) != round(new_percent, 1):
            changed_logs += 1
            exercise_name = log.exercise.name if log.exercise else f'#{log.exercise_id}'
            print(f'  подход {log.id} ({exercise_name}, подход {log.set_number}): '
                  f'{old_percent:.1f}% → {new_percent:.1f}%')

    # Итоги пересчитываем у всех тренировок: правила подсчёта процента и тоннажа могли измениться.
    # Тренировки без подходов не трогаем: у некоторых старых подходы были потеряны,
    # и сохранённый итог — единственное, что от них осталось.
    changed_sessions = 0
    kept_without_logs = 0
    for session in WorkoutSession.query.order_by(WorkoutSession.date).all():
        if not SetLog.query.filter_by(session_id=session.id).count():
            if session.completion_percent or session.total_tonnage:
                kept_without_logs += 1
            continue
        percent, tonnage = session_totals(session)
        old_percent, old_tonnage = round(session.completion_percent or 0, 1), round(session.total_tonnage or 0, 1)
        if old_percent != percent or old_tonnage != round(tonnage, 1):
            changed_sessions += 1
            print(f'  тренировка {session.id} от {session.date:%d.%m.%Y}: '
                  f'{old_percent:.1f}% → {percent:.1f}%, тоннаж {old_tonnage:.0f} → {tonnage:.0f} кг')
            session.completion_percent, session.total_tonnage = percent, tonnage

    print(f'\nПодходов с изменённым процентом: {changed_logs}')
    print(f'Тренировок с изменённым итогом: {changed_sessions}')
    if kept_without_logs:
        print(f'Тренировок без подходов, итог оставлен как есть: {kept_without_logs}')

    if not apply_changes:
        db.session.rollback()
        print('\nЭто пробный запуск, БД не изменена. Для записи: python recalc_stats.py --apply')
        return

    db.session.commit()
    print('\n✅ Изменения записаны в БД')


if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        recalc(apply_changes='--apply' in sys.argv)
