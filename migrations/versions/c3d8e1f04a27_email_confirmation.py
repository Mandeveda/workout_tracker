"""Подтверждение почты: дата подтверждения, срок, новый адрес на подтверждении.

Revision ID: c3d8e1f04a27
Revises: b7e2a9c41d03
Create Date: 2026-10-24

У уже зарегистрированных пользователей почта не подтверждалась: им даётся 30 дней
с момента применения миграции (а не с даты регистрации — иначе срок истёк бы сразу).
"""
from datetime import datetime, timedelta

from alembic import op
import sqlalchemy as sa


revision = 'c3d8e1f04a27'
down_revision = 'b7e2a9c41d03'
branch_labels = None
depends_on = None

EMAIL_CONFIRM_DAYS = 30


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email_confirmed_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('email_confirm_deadline', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('pending_email', sa.String(length=120), nullable=True))

    deadline = datetime.utcnow() + timedelta(days=EMAIL_CONFIRM_DAYS)
    op.get_bind().execute(
        sa.text('UPDATE users SET email_confirm_deadline = :deadline WHERE email_confirmed_at IS NULL'),
        {'deadline': deadline}
    )


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('pending_email')
        batch_op.drop_column('email_confirm_deadline')
        batch_op.drop_column('email_confirmed_at')
