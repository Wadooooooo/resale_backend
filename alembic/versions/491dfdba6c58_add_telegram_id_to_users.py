"""add_telegram_id_to_users

Revision ID: 491dfdba6c58
Revises: 210ada4775f1
Create Date: 2025-08-18 23:53:12.835249

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '491dfdba6c58'
down_revision: Union[str, Sequence[str], None] = '210ada4775f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('telegram_id', sa.Integer(), nullable=True))
    op.create_index('ix_users_telegram_id', 'users', ['telegram_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_users_telegram_id', table_name='users')
    op.drop_column('users', 'telegram_id')