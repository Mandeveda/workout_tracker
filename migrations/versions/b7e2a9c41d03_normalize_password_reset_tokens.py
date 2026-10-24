"""Таблица password_reset_tokens в стандартном виде.

Revision ID: b7e2a9c41d03
Revises: 5999db948d2c
Create Date: 2026-10-24

На рабочей базе таблица была создана вручную (`id INTEGER PRIMARY KEY AUTOINCREMENT`,
`token ... UNIQUE` прямо в описании колонки). По смыслу это та же схема, но сравнение
схемы (`flask db migrate` / `flask db check`) не распознаёт такую запись и каждый раз
предлагало «добавить» уникальность и NOT NULL. Миграция пересоздаёт таблицу так, как её
описывает модель, и переносит все строки. На базах, созданных начальной миграцией,
таблица уже стандартная — там ничего не происходит.
"""
from alembic import op
import sqlalchemy as sa


revision = 'b7e2a9c41d03'
down_revision = '5999db948d2c'
branch_labels = None
depends_on = None

COLUMNS = 'id, user_id, token, expires_at, created_at, used'


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != 'sqlite':
        return
    ddl = bind.execute(sa.text(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'password_reset_tokens'"
    )).scalar() or ''
    if 'AUTOINCREMENT' not in ddl.upper():
        return  # таблица уже в стандартном виде

    op.rename_table('password_reset_tokens', 'password_reset_tokens_old')
    op.create_table('password_reset_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=100), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('used', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token')
    )
    op.execute(f'INSERT INTO password_reset_tokens ({COLUMNS}) SELECT {COLUMNS} FROM password_reset_tokens_old')
    op.drop_table('password_reset_tokens_old')


def downgrade():
    pass  # схема по смыслу та же — возвращать ручной вид таблицы незачем
