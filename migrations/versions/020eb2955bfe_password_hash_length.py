"""Поле хэша пароля — 256 символов.

Revision ID: 020eb2955bfe
Revises: acd378e663a7
Create Date: 2026-10-25

Хэш scrypt (Werkzeug по умолчанию) — 162 символа, а поле было VARCHAR(128). SQLite длину
не проверяет, MySQL — отказывает в записи: без этой миграции после переезда не работали бы
регистрация и смена пароля.
"""
from alembic import op
import sqlalchemy as sa


revision = '020eb2955bfe'
down_revision = 'acd378e663a7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('password_hash', existing_type=sa.VARCHAR(length=128),
                              type_=sa.String(length=256), existing_nullable=True)


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('password_hash', existing_type=sa.String(length=256),
                              type_=sa.VARCHAR(length=128), existing_nullable=True)
