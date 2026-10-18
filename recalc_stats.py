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
from app.routes.workouts import update_session_completion


def recalc(apply_changes):
    changed_logs = 0
    sessions_to_update = set()

    for log in SetLog.query.all():
        old_percent = log.completion_percent or 0
        user_weight = log.session.user.weight if log.session and log.session.user else None
        new_percent = log.calculate_completion(user_weight)

        if round(old_percent, 1) != round(new_percent, 1):
            changed_logs += 1
            sessions_to_update.add(log.session_id)
            exercise_name = log.exercise.name if log.exercise else f'#{log.exercise_id}'
            print(f'  подход {log.id} ({exercise_name}, подход {log.set_number}): '
                  f'{old_percent:.1f}% → {new_percent:.1f}%')

    changed_sessions = 0
    for session in WorkoutSession.query.filter(WorkoutSession.id.in_(sessions_to_update)).all():
        logs = SetLog.query.filter_by(session_id=session.id).all()
        new_percent = round(sum(l.completion_percent for l in logs) / len(logs), 1) if logs else 0
        if round(session.completion_percent or 0, 1) != new_percent:
            changed_sessions += 1
            print(f'  тренировка {session.id} от {session.date:%d.%m.%Y}: '
                  f'{session.completion_percent or 0:.1f}% → {new_percent:.1f}%')

    print(f'\nПодходов с изменённым процентом: {changed_logs}')
    print(f'Тренировок с изменённым итогом: {changed_sessions}')

    if not apply_changes:
        db.session.rollback()
        print('\nЭто пробный запуск, БД не изменена. Для записи: python recalc_stats.py --apply')
        return

    db.session.commit()
    for session_id in sessions_to_update:
        update_session_completion(session_id)
    print('\n✅ Изменения записаны в БД')


if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        recalc(apply_changes='--apply' in sys.argv)
