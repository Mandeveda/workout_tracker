"""История тренировок переживает удаление шаблона.

Revision ID: caa4b879a4a6
Revises: c3d8e1f04a27
Create Date: 2026-10-25

- workout_sessions.template_name — название шаблона на момент тренировки (заполняется
  для уже проведённых тренировок из их шаблонов);
- workout_schedules.template_id может быть пустым — у дней проведённых тренировок
  удалённого шаблона.
"""
from alembic import op
import sqlalchemy as sa


revision = 'caa4b879a4a6'
down_revision = 'c3d8e1f04a27'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('workout_schedules', schema=None) as batch_op:
        batch_op.alter_column('template_id', existing_type=sa.INTEGER(), nullable=True)

    with op.batch_alter_table('workout_sessions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('template_name', sa.String(length=100), nullable=True))

    op.execute(
        'UPDATE workout_sessions SET template_name = '
        '(SELECT name FROM workout_templates WHERE workout_templates.id = workout_sessions.template_id) '
        'WHERE template_id IS NOT NULL'
    )


def downgrade():
    with op.batch_alter_table('workout_sessions', schema=None) as batch_op:
        batch_op.drop_column('template_name')

    # строки без шаблона не вернуть в NOT NULL — откат возможен, только пока их нет
    with op.batch_alter_table('workout_schedules', schema=None) as batch_op:
        batch_op.alter_column('template_id', existing_type=sa.INTEGER(), nullable=False)
