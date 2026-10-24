"""Отметка «был на сайте» у пользователя.

Revision ID: acd378e663a7
Revises: caa4b879a4a6
Create Date: 2026-10-25

Для уже зарегистрированных заполняется датой последней тренировки — точнее
неизвестно; у кого тренировок нет, остаётся пусто («ещё не заходил»), пока не зайдёт.
"""
from alembic import op
import sqlalchemy as sa


revision = 'acd378e663a7'
down_revision = 'caa4b879a4a6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_seen_at', sa.DateTime(), nullable=True))

    op.execute(
        'UPDATE users SET last_seen_at = '
        '(SELECT MAX(date) FROM workout_sessions WHERE workout_sessions.user_id = users.id)'
    )


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('last_seen_at')
