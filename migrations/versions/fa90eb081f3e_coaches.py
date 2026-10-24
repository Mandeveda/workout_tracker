"""Тренеры: анкеты, специализации, связь с подопечными, комментарии, отзывы, уведомления.

Revision ID: fa90eb081f3e
Revises: 020eb2955bfe
Create Date: 2026-10-25

Только новые таблицы и пустые колонки — существующие данные не меняются.
Начальный список специализаций админ потом правит в админке.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fa90eb081f3e'
down_revision = '020eb2955bfe'
branch_labels = None
depends_on = None

SPECIALIZATIONS = [
    'Набор мышечной массы', 'Снижение веса', 'Силовой тренинг и пауэрлифтинг', 'Функциональный тренинг',
    'Бег и выносливость', 'Растяжка и мобильность', 'Восстановление после травм', 'Тренировки дома без оборудования',
    'Подготовка к соревнованиям', 'Для начинающих',
]


def upgrade():
    op.create_table('specializations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=60), nullable=False),
    sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.bulk_insert(sa.table('specializations', sa.column('name', sa.String), sa.column('sort_order', sa.Integer)),
                   [{'name': name, 'sort_order': n} for n, name in enumerate(SPECIALIZATIONS, start=1)])
    op.create_table('coach_links',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('coach_id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('message', sa.String(length=500), nullable=True),
    sa.Column('share_measurements', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('answered_at', sa.DateTime(), nullable=True),
    sa.Column('ended_at', sa.DateTime(), nullable=True),
    sa.Column('ended_by_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['client_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['coach_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['ended_by_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('coach_links', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_coach_links_client_id'), ['client_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_coach_links_coach_id'), ['coach_id'], unique=False)

    op.create_table('coach_profiles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('bio', sa.Text(), nullable=True),
    sa.Column('experience_years', sa.Integer(), nullable=True),
    sa.Column('city', sa.String(length=80), nullable=True),
    sa.Column('works_online', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('works_offline', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('contacts', sa.String(length=300), nullable=True),
    sa.Column('photo', sa.String(length=100), nullable=True),
    sa.Column('max_clients', sa.Integer(), nullable=True),
    sa.Column('accepting', sa.Boolean(), server_default='1', nullable=False),
    sa.Column('admin_note', sa.String(length=300), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('approved_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )
    op.create_table('coach_reviews',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('coach_id', sa.Integer(), nullable=False),
    sa.Column('author_id', sa.Integer(), nullable=False),
    sa.Column('rating', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=True),
    sa.Column('reply', sa.Text(), nullable=True),
    sa.Column('replied_at', sa.DateTime(), nullable=True),
    sa.Column('reported_at', sa.DateTime(), nullable=True),
    sa.Column('is_hidden', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['coach_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('coach_id', 'author_id', name='uq_coach_review_author')
    )
    with op.batch_alter_table('coach_reviews', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_coach_reviews_coach_id'), ['coach_id'], unique=False)

    op.create_table('notifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('text', sa.String(length=300), nullable=False),
    sa.Column('url', sa.String(length=300), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('read_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.create_index('ix_notifications_user_read', ['user_id', 'read_at'], unique=False)

    op.create_table('coach_specializations',
    sa.Column('coach_profile_id', sa.Integer(), nullable=False),
    sa.Column('specialization_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['coach_profile_id'], ['coach_profiles.id'], ),
    sa.ForeignKeyConstraint(['specialization_id'], ['specializations.id'], ),
    sa.PrimaryKeyConstraint('coach_profile_id', 'specialization_id')
    )
    op.create_table('session_comments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('author_id', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['session_id'], ['workout_sessions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('session_comments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_session_comments_session_id'), ['session_id'], unique=False)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email_notifications', sa.Boolean(), server_default='1', nullable=False))

    with op.batch_alter_table('workout_schedules', schema=None) as batch_op:
        batch_op.add_column(sa.Column('assigned_by_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_workout_schedules_assigned_by', 'users', ['assigned_by_id'], ['id'])

    with op.batch_alter_table('workout_templates', schema=None) as batch_op:
        batch_op.add_column(sa.Column('assigned_by_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_workout_templates_assigned_by', 'users', ['assigned_by_id'], ['id'])



def downgrade():
    with op.batch_alter_table('workout_templates', schema=None) as batch_op:
        batch_op.drop_constraint('fk_workout_templates_assigned_by', type_='foreignkey')
        batch_op.drop_column('assigned_by_id')

    with op.batch_alter_table('workout_schedules', schema=None) as batch_op:
        batch_op.drop_constraint('fk_workout_schedules_assigned_by', type_='foreignkey')
        batch_op.drop_column('assigned_by_id')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('email_notifications')

    with op.batch_alter_table('session_comments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_session_comments_session_id'))

    op.drop_table('session_comments')
    op.drop_table('coach_specializations')
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_index('ix_notifications_user_read')

    op.drop_table('notifications')
    with op.batch_alter_table('coach_reviews', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_coach_reviews_coach_id'))

    op.drop_table('coach_reviews')
    op.drop_table('coach_profiles')
    with op.batch_alter_table('coach_links', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_coach_links_coach_id'))
        batch_op.drop_index(batch_op.f('ix_coach_links_client_id'))

    op.drop_table('coach_links')
    op.drop_table('specializations')
