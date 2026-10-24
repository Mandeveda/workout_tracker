"""Удаление шаблона с историей и пользователя со всеми данными (ROADMAP B).

Удаление идёт массовыми запросами в правильном порядке (сначала то, что ссылается,
потом то, на что ссылаются), а не через каскады ORM: каскад «шаблон → упражнения
шаблона → подходы» стёр бы подходы проведённых тренировок, а «шаблон → расписание» —
дни, к которым привязаны тренировки из истории. commit делает вызывающий код.
"""
from sqlalchemy import or_

from app import db
from app.models import (CoachLink, CoachProfile, CoachReview, Exercise, Notification, PasswordResetToken,
                        SessionComment, SetLog, TemplateExercise, WorkoutSchedule, WorkoutSession,
                        WorkoutTemplate, coach_specializations)


def _template_sessions(template):
    schedule_ids = db.session.query(WorkoutSchedule.id).filter(WorkoutSchedule.template_id == template.id)
    return WorkoutSession.query.filter(or_(WorkoutSession.template_id == template.id,
                                           WorkoutSession.schedule_id.in_(schedule_ids)))


def template_deletion_preview(template):
    """Что произойдёт с шаблоном: сколько тренировок останется в истории, сколько дней уйдёт из расписания"""
    kept = _template_sessions(template).filter(
        or_(WorkoutSession.is_completed.is_(True), WorkoutSession.status == 'completed',
            WorkoutSession.set_logs.any())).all()
    kept_schedule_ids = {s.schedule_id for s in kept if s.schedule_id}
    days = WorkoutSchedule.query.filter_by(template_id=template.id).count() - len(kept_schedule_ids)
    return {'kept_sessions': len(kept), 'removed_days': max(0, days)}


def delete_template(template):
    """Удаляет шаблон. Начатые тренировки остаются в истории с названием шаблона,
    дни расписания без начатой тренировки удаляются."""
    from app.routes.workouts import session_totals  # иначе циклический импорт

    te_ids = [te.id for te in template.template_exercises]
    in_template = {str(te.exercise_id) for te in template.template_exercises}

    for session in _template_sessions(template).all():
        # status — для старых записей, у которых is_completed пуст (колонку добавили позже)
        finished = session.is_completed or session.status == 'completed'
        if not finished and not session.set_logs:
            SessionComment.query.filter_by(session_id=session.id).delete(synchronize_session=False)
            db.session.delete(session)        # открыли и ничего не записали — в истории не нужна
            continue
        if not finished:
            # незавершённую тренировку завершаем с тем, что уже записано: без шаблона её не продолжить
            session.completion_percent, session.total_tonnage = session_totals(session)
            session.is_completed, session.status = True, 'completed'
        session.template_name = session.template_name or template.name
        session.template_id = None
        if session.schedule:
            # план подходов считается по упражнениям шаблона — фиксируем его состав на момент удаления
            session.schedule.planned_data = {k: v for k, v in (session.schedule.planned_data or {}).items()
                                             if k in in_template}
            session.schedule.template_id = None
            session.schedule.status = 'completed'
    db.session.flush()

    if te_ids:
        SetLog.query.filter(SetLog.template_exercise_id.in_(te_ids)).update(
            {SetLog.template_exercise_id: None}, synchronize_session=False)
    WorkoutSchedule.query.filter_by(template_id=template.id).delete(synchronize_session=False)
    TemplateExercise.query.filter_by(template_id=template.id).delete(synchronize_session=False)
    db.session.expire_all()                 # коллекции шаблона в памяти устарели после массовых запросов
    db.session.delete(template)


def user_deletion_preview(user):
    """Перечень того, что пропадёт вместе с пользователем"""
    sessions = db.session.query(WorkoutSession.id).filter(WorkoutSession.user_id == user.id)
    return {
        'templates': WorkoutTemplate.query.filter_by(user_id=user.id).count(),
        'schedules': WorkoutSchedule.query.filter_by(user_id=user.id).count(),
        'sessions': WorkoutSession.query.filter_by(user_id=user.id).count(),
        'sets': SetLog.query.filter(SetLog.session_id.in_(sessions)).count(),
        'measurements': len(user.measurements_history or []),
        'exercises': Exercise.query.filter_by(created_by_id=user.id).count(),
    }


def delete_user(user, heir):
    """Удаляет пользователя со всеми данными. Его упражнения каталога (им пользуются другие)
    переходят к heir — администратору, который удаляет."""
    sessions = db.session.query(WorkoutSession.id).filter(WorkoutSession.user_id == user.id)
    templates = db.session.query(WorkoutTemplate.id).filter(WorkoutTemplate.user_id == user.id)

    Exercise.query.filter_by(created_by_id=user.id).update(
        {Exercise.created_by_id: heir.id}, synchronize_session=False)
    # как тренер: шаблоны и дни, назначенные подопечным, остаются у них — без пометки «от тренера»
    for model in (WorkoutTemplate, WorkoutSchedule):
        model.query.filter_by(assigned_by_id=user.id).update({model.assigned_by_id: None}, synchronize_session=False)
    profile_ids = db.session.query(CoachProfile.id).filter(CoachProfile.user_id == user.id)
    db.session.execute(coach_specializations.delete().where(coach_specializations.c.coach_profile_id.in_(profile_ids)))
    CoachProfile.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    CoachLink.query.filter(or_(CoachLink.coach_id == user.id, CoachLink.client_id == user.id)).delete(
        synchronize_session=False)
    CoachReview.query.filter(or_(CoachReview.coach_id == user.id, CoachReview.author_id == user.id)).delete(
        synchronize_session=False)
    SessionComment.query.filter(or_(SessionComment.author_id == user.id, SessionComment.session_id.in_(sessions))).delete(
        synchronize_session=False)
    Notification.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    SetLog.query.filter(SetLog.session_id.in_(sessions)).delete(synchronize_session=False)
    WorkoutSession.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    WorkoutSchedule.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    TemplateExercise.query.filter(TemplateExercise.template_id.in_(templates)).delete(synchronize_session=False)
    WorkoutTemplate.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    PasswordResetToken.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    db.session.expire_all()
    db.session.delete(user)
