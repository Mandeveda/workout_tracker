"""Подтверждение почты: подписанная ссылка и письмо.

Ссылка — подписанный секретным ключом сайта токен с id пользователя и адресом,
который подтверждается; действует EMAIL_LINK_DAYS дней. Отдельной таблицы не нужно:
после подтверждения или смены адреса старая ссылка просто перестаёт совпадать.
"""
from flask import current_app, render_template, url_for
from flask_mail import Message
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app import mail

EMAIL_LINK_DAYS = 3
_SALT = 'email-confirm'


def _serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt=_SALT)


def make_token(user, email):
    return _serializer().dumps({'uid': user.id, 'email': email})


def read_token(token):
    """(id пользователя, адрес) из ссылки, либо (None, причина): 'expired' или 'invalid'"""
    try:
        data = _serializer().loads(token, max_age=EMAIL_LINK_DAYS * 24 * 3600)
    except SignatureExpired:
        return None, 'expired'
    except BadSignature:
        return None, 'invalid'
    return (data.get('uid'), data.get('email')), None


def send_confirmation(user, email):
    """Письмо со ссылкой подтверждения на email (текущий адрес или новый при смене)"""
    url = url_for('auth.confirm_email', token=make_token(user, email), _external=True,
                  _scheme=current_app.config.get('PREFERRED_URL_SCHEME', 'http'))
    is_change = bool(user.pending_email) and email == user.pending_email
    html = render_template('emails/confirm_email.html', user=user, url=url, is_change=is_change,
                           link_days=EMAIL_LINK_DAYS)
    text = (f'Здравствуйте, {user.username}!\n\nПодтвердите почту для Tracker Workout по ссылке '
            f'(действует {EMAIL_LINK_DAYS} дня):\n{url}\n\nЕсли вы не регистрировались, удалите это письмо.')
    mail.send(Message(subject='Подтвердите почту — Tracker Workout', recipients=[email], html=html, body=text,
                      sender=current_app.config.get('MAIL_DEFAULT_SENDER') or current_app.config.get('MAIL_USERNAME')))
