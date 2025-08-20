"""create_waiting_list_table

Revision ID: aa8f28231f8f
Revises: d87a4ba2ecfd
Create Date: 2025-08-20 17:19:59.920254

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'aa8f28231f8f'
down_revision: Union[str, Sequence[str], None] = 'd87a4ba2ecfd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Creates the waiting_list table."""
    op.create_table('waiting_list',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('customer_name', sa.String(length=255), nullable=False),
    sa.Column('customer_phone', sa.String(length=50), nullable=True),
    sa.Column('model_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['model_id'], ['models.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # Добавляем индекс на колонку status для ускорения фильтрации
    op.create_index(op.f('ix_waiting_list_status'), 'waiting_list', ['status'], unique=False)


def downgrade() -> None:
    """Drops the waiting_list table."""
    op.drop_index(op.f('ix_waiting_list_status'), table_name='waiting_list')
    op.drop_table('waiting_list')