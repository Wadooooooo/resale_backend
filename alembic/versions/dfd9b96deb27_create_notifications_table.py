"""create_notifications_table

Revision ID: dfd9b96deb27
Revises: aa8f28231f8f
Create Date: 2025-08-20 19:04:23.563364

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dfd9b96deb27'
down_revision: Union[str, Sequence[str], None] = 'aa8f28231f8f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Creates the notifications table."""
    op.create_table('notifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('message', sa.String(length=512), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('waiting_list_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['waiting_list_id'], ['waiting_list.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    # Индекс для ускорения поиска непрочитанных уведомлений для пользователя
    op.create_index(op.f('ix_notifications_user_id_is_read'), 'notifications', ['user_id', 'is_read'], unique=False)


def downgrade() -> None:
    """Drops the notifications table."""
    op.drop_index(op.f('ix_notifications_user_id_is_read'), table_name='notifications')
    op.drop_table('notifications')