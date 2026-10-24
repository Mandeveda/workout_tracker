"""ROADMAP A: подтверждение почты ссылкой, напоминание, смена адреса, пометки в админке"""
import re
from datetime import datetime, timedelta
from unittest import mock

from app import db, mail
from app import email_confirm
from app.models import User
from tests.conftest import PASSWORD, login


def link_from(message):
    return re.search(r'(/auth/confirm_email/[\w.\-]+)', message.body).group(1)


def test_register_sends_confirmation_link_and_link_confirms(client):
    with mail.record_messages() as outbox:
        response = client.post('/auth/register', data={'username': 'newbie', 'email': 'NewBie@Mail.ru',
                                                       'password': PASSWORD, 'confirm_password': PASSWORD})
    assert response.status_code == 302
    assert len(outbox) == 1 and outbox[0].recipients == ['newbie@mail.ru']
    user = User.query.filter_by(username='newbie').one()
    assert not user.email_confirmed
    assert user.email_confirm_days_left() in (29, 30)

    client.get(link_from(outbox[0]))
    db.session.refresh(user)
    assert user.email_confirmed


def test_registration_survives_mail_failure(client):
    with mock.patch('app.email_confirm.mail.send', side_effect=OSError('smtp down')):
        response = client.post('/auth/register', data={'username': 'newbie', 'email': 'newbie@mail.ru',
                                                       'password': PASSWORD, 'confirm_password': PASSWORD},
                               follow_redirects=True)
    assert 'Письмо для подтверждения почты отправить не удалось' in response.get_data(as_text=True)
    assert User.query.filter_by(username='newbie').count() == 1


def test_expired_and_forged_links_do_not_confirm(app, client, make_user):
    user = make_user('ivan')
    token = email_confirm.make_token(user, user.email)
    later = datetime.utcnow() + timedelta(days=email_confirm.EMAIL_LINK_DAYS + 1)
    with mock.patch('itsdangerous.timed.time.time', return_value=later.timestamp()):
        page = client.get(f'/auth/confirm_email/{token}', follow_redirects=True).get_data(as_text=True)
    assert 'Ссылка устарела' in page
    page = client.get(f'/auth/confirm_email/{token[:-3]}xyz', follow_redirects=True).get_data(as_text=True)
    assert 'Ссылка недействительна' in page
    db.session.refresh(user)
    assert not user.email_confirmed


def test_banner_counts_days_and_resend_goes_to_current_address(client, make_user):
    make_user('ivan', email_confirm_deadline=datetime.utcnow() + timedelta(days=12, hours=1))
    login(client, 'ivan')
    page = client.get('/dashboard').get_data(as_text=True)
    assert 'email-banner' in page and '12' in page

    with mail.record_messages() as outbox:
        client.post('/auth/resend_confirmation', data={'next': 'https://evil.example/'})
    assert outbox[0].recipients == ['ivan@example.com']


def test_no_banner_once_confirmed(client, make_user):
    make_user('ivan', email_confirmed_at=datetime.utcnow())
    login(client, 'ivan')
    assert 'email-banner' not in client.get('/dashboard').get_data(as_text=True)
    with mail.record_messages() as outbox:
        client.post('/auth/resend_confirmation')
    assert outbox == []


def test_overdue_banner(client, make_user):
    make_user('ivan', email_confirm_deadline=datetime.utcnow() - timedelta(days=1))
    login(client, 'ivan')
    assert 'is-overdue' in client.get('/dashboard').get_data(as_text=True)


def test_change_email_applies_only_after_confirmation(client, make_user):
    user = make_user('ivan', email_confirmed_at=datetime.utcnow())
    login(client, 'ivan')
    with mail.record_messages() as outbox:
        client.post('/profile/change_email', data={'new_email': 'Ivan.New@mail.ru', 'password': PASSWORD})
    db.session.refresh(user)
    assert user.email == 'ivan@example.com' and user.pending_email == 'ivan.new@mail.ru'
    assert outbox[0].recipients == ['ivan.new@mail.ru']

    client.get(link_from(outbox[0]))
    db.session.refresh(user)
    assert user.email == 'ivan.new@mail.ru' and user.pending_email is None and user.email_confirmed


def test_change_email_requires_password_and_free_address(client, make_user):
    user = make_user('ivan')
    make_user('petr')
    login(client, 'ivan')
    with mail.record_messages() as outbox:
        client.post('/profile/change_email', data={'new_email': 'new@mail.ru', 'password': 'wrong'})
        client.post('/profile/change_email', data={'new_email': 'PETR@example.com', 'password': PASSWORD})
    db.session.refresh(user)
    assert user.pending_email is None and outbox == []


def test_address_taken_before_confirmation_is_not_applied(client, make_user):
    user = make_user('ivan')
    login(client, 'ivan')
    with mail.record_messages() as outbox:
        client.post('/profile/change_email', data={'new_email': 'new@mail.ru', 'password': PASSWORD})
    make_user('petr', email='new@mail.ru')        # адрес занял кто-то другой, пока письмо шло
    client.get(link_from(outbox[0]))
    db.session.refresh(user)
    assert user.email == 'ivan@example.com'


def test_cancel_email_change_invalidates_link(client, make_user):
    user = make_user('ivan')
    login(client, 'ivan')
    with mail.record_messages() as outbox:
        client.post('/profile/change_email', data={'new_email': 'new@mail.ru', 'password': PASSWORD})
    client.post('/profile/cancel_email_change')
    client.get(link_from(outbox[0]))
    db.session.refresh(user)
    assert user.email == 'ivan@example.com' and user.pending_email is None and not user.email_confirmed


def test_admin_sees_unconfirmed_and_overdue(client, make_user):
    make_user('boss', role_id=1, email_confirmed_at=datetime.utcnow())
    make_user('fresh')
    make_user('late', email_confirm_deadline=datetime.utcnow() - timedelta(days=2))
    login(client, 'boss')
    overdue = client.get('/admin/users?show=overdue').get_data(as_text=True)
    assert 'late' in overdue and 'fresh' not in overdue and 'срок подтверждения истёк' in overdue
    unconfirmed = client.get('/admin/users?show=unconfirmed').get_data(as_text=True)
    assert 'late' in unconfirmed and 'fresh' in unconfirmed and 'boss@example.com' not in unconfirmed
