"""ROADMAP B: удаление шаблона с историей и пользователя со всеми данными"""
from datetime import date, datetime, timedelta

from app import db
from app.models import (Exercise, PasswordResetToken, SetLog, TemplateExercise, User,
                        WorkoutSchedule, WorkoutSession, WorkoutTemplate)
from app.routes.workouts import session_totals
from tests.conftest import login

PLAN = {'sets': 3, 'reps': 10, 'weight': 50}


def template_with_history(owner, make_exercise, make_template, make_session):
    """Шаблон: проведённая тренировка (1 из 3 подходов), пропущенный день и день в будущем"""
    squat = make_exercise('Присед')
    template, done_day = make_template(owner, [(squat, PLAN)], on=date.today() - timedelta(days=7))
    done_day.status = 'completed'
    session = make_session(owner, done_day, completed=True, days_ago=7, logs=[(squat, 10, 50)])
    session.template_name = template.name
    session.completion_percent, session.total_tonnage = session_totals(session)
    for days, status in ((-3, 'skipped'), (3, 'planned')):
        db.session.add(WorkoutSchedule(user_id=owner.id, template_id=template.id, status=status,
                                       scheduled_date=date.today() + timedelta(days=days),
                                       planned_data={str(squat.id): PLAN}))
    db.session.commit()
    return template, session


def test_template_with_history_is_deleted_but_history_stays(client, make_user, make_exercise,
                                                             make_template, make_session):
    owner = make_user('ivan')
    template, session = template_with_history(owner, make_exercise, make_template, make_session)
    percent_before = session.completion_percent
    login(client, 'ivan')

    page = client.post(f'/templates/delete/{template.id}', follow_redirects=True).get_data(as_text=True)
    assert 'Шаблон «День ног» удалён' in page and '2 дня' in page
    assert WorkoutTemplate.query.count() == 0 and TemplateExercise.query.count() == 0
    # остался только день проведённой тренировки, без шаблона
    assert [(s.status, s.template_id) for s in WorkoutSchedule.query.all()] == [('completed', None)]

    session = db.session.get(WorkoutSession, session.id)
    assert session.template_id is None and session.template_name == 'День ног'
    assert SetLog.query.filter_by(session_id=session.id).count() == 1
    # процент считается от тех же 3 запланированных подходов, что и до удаления
    assert session_totals(session)[0] == percent_before == round(100 / 3, 1)

    summary = client.get(f'/workouts/summary/{session.id}')
    assert summary.status_code == 200 and 'День ног' in summary.get_data(as_text=True)
    assert 'День ног' in client.get('/dashboard').get_data(as_text=True)
    assert client.get('/analytics/dashboard').status_code == 200


def test_unfinished_sessions_on_deleted_template(client, make_user, make_exercise, make_template, make_session):
    owner = make_user('ivan')
    squat = make_exercise('Присед')
    template, today = make_template(owner, [(squat, PLAN)])
    started = make_session(owner, today, logs=[(squat, 10, 50)])      # начата, подход записан
    _, other_day = make_template(owner, [(squat, PLAN)], name='Пустой')
    WorkoutSchedule.query.get(other_day.id).template_id = template.id
    empty = make_session(owner, other_day)                            # открыта, ничего не записано
    login(client, 'ivan')
    client.post(f'/templates/delete/{template.id}')

    started = db.session.get(WorkoutSession, started.id)
    assert started.is_completed and started.template_name == 'День ног' and started.total_tonnage == 500
    assert db.session.get(WorkoutSession, empty.id) is None


def test_only_owner_or_admin_deletes_template(client, make_user, make_exercise, make_template, make_session):
    owner = make_user('ivan')
    make_user('petr')
    make_user('boss', role_id=1)
    template, _ = template_with_history(owner, make_exercise, make_template, make_session)
    login(client, 'petr')
    client.post(f'/templates/delete/{template.id}')
    assert db.session.get(WorkoutTemplate, template.id) is not None

    client.post('/auth/logout')
    login(client, 'boss')
    client.post(f'/templates/delete/{template.id}')
    assert db.session.get(WorkoutTemplate, template.id) is None
    assert WorkoutSession.query.filter_by(user_id=owner.id).count() == 1


def test_admin_deletes_user_with_all_data(client, make_user, make_exercise, make_template, make_session):
    boss = make_user('boss', role_id=1)
    expert = make_user('expert', role_id=3, measurements_history=[{'weight': 80}])
    other = make_user('other')
    own_exercise = make_exercise('Жим гантелей', author=expert)
    template_with_history(expert, make_exercise, make_template, make_session)
    _, other_day = make_template(other, [(own_exercise, PLAN)], name='Чужой')   # другой пользуется его упражнением
    make_session(other, other_day, completed=True, logs=[(own_exercise, 10, 20)])
    db.session.add(PasswordResetToken(user_id=expert.id, token='t', expires_at=datetime.utcnow()))
    db.session.commit()
    expert_id = expert.id
    login(client, 'boss')

    page = client.get(f'/admin/user/{expert_id}/delete').get_data(as_text=True)
    assert 'Удалить expert?' in page and '1</b> замер' in page and 'их автором станете вы' in page

    client.post(f'/admin/user/{expert_id}/delete', data={'confirm_username': 'Expert'})
    assert db.session.get(User, expert_id) is not None                     # имя введено неверно

    client.post(f'/admin/user/{expert_id}/delete', data={'confirm_username': 'expert'})
    db.session.expire_all()
    assert db.session.get(User, expert_id) is None
    for model in (WorkoutTemplate, WorkoutSchedule, WorkoutSession, PasswordResetToken):
        assert model.query.filter_by(user_id=expert_id).count() == 0
    assert Exercise.query.filter_by(created_by_id=expert_id).count() == 0
    assert db.session.get(Exercise, own_exercise.id).created_by_id == boss.id
    # данные другого пользователя целы
    assert WorkoutSession.query.filter_by(user_id=other.id).count() == 1
    assert SetLog.query.join(WorkoutSession).filter(WorkoutSession.user_id == other.id).count() == 1


def test_admin_cannot_delete_admin_or_self(client, make_user):
    boss = make_user('boss', role_id=1)
    second = make_user('second', role_id=1)
    login(client, 'boss')
    for target in (boss, second):
        client.post(f'/admin/user/{target.id}/delete', data={'confirm_username': target.username})
    assert User.query.count() == 2


def test_only_admin_opens_delete_page(client, make_user):
    victim = make_user('victim')
    make_user('ivan')
    login(client, 'ivan')
    assert client.get(f'/admin/user/{victim.id}/delete').status_code == 302
    client.post(f'/admin/user/{victim.id}/delete', data={'confirm_username': 'victim'})
    assert db.session.get(User, victim.id) is not None


def test_legacy_completed_session_is_not_recalculated(client, make_user, make_exercise, make_template, make_session):
    """Старые записи: status='completed', а is_completed пуст — их итоги не трогаем"""
    owner = make_user('ivan')
    squat = make_exercise('Присед')
    template, day = make_template(owner, [(squat, PLAN)])
    session = make_session(owner, day, logs=[(squat, 10, 50)])
    session.is_completed, session.status, session.completion_percent = None, 'completed', 5.7
    db.session.commit()
    login(client, 'ivan')
    client.post(f'/templates/delete/{template.id}')
    session = db.session.get(WorkoutSession, session.id)
    assert session.completion_percent == 5.7 and session.template_name == 'День ног'


def test_deleting_coach_or_client_cleans_coach_data(client, make_user, make_exercise, make_template, make_session):
    """ROADMAP D.1: у удалённого тренера пропадают анкета, связи, отзывы; назначенное подопечному остаётся"""
    from app.models import (CoachLink, CoachProfile, CoachReview, Notification, SessionComment,
                            Specialization)
    make_user('boss', role_id=1)
    coach, pupil = make_user('coach'), make_user('pupil')
    profile = CoachProfile(user_id=coach.id, status='approved', specializations=[Specialization.query.first()]
                           if Specialization.query.first() else [])
    squat = make_exercise('Присед')
    template, day = make_template(pupil, [(squat, PLAN)])
    template.assigned_by_id = day.assigned_by_id = coach.id
    session = make_session(pupil, day, completed=True, logs=[(squat, 10, 50)])
    db.session.add_all([profile,
                        CoachLink(coach_id=coach.id, client_id=pupil.id, status='active'),
                        CoachReview(coach_id=coach.id, author_id=pupil.id, rating=5, text='Отлично'),
                        SessionComment(session_id=session.id, author_id=coach.id, text='Молодец'),
                        Notification(user_id=coach.id, kind='coach_request', text='Новая заявка')])
    db.session.commit()
    login(client, 'boss')
    client.post(f'/admin/user/{coach.id}/delete', data={'confirm_username': 'coach'})
    db.session.expire_all()

    assert db.session.get(User, coach.id) is None
    for model in (CoachProfile, CoachLink, CoachReview, SessionComment, Notification):
        assert model.query.count() == 0, model
    template = db.session.get(WorkoutTemplate, template.id)
    assert template is not None and template.assigned_by_id is None
    assert WorkoutSchedule.query.filter_by(user_id=pupil.id).one().assigned_by_id is None
    assert SetLog.query.count() == 1
