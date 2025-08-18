"""add_telegram_id_to_users

Revision ID: 210ada4775f1
Revises: 236f8ebc042e
Create Date: 2025-08-18 23:25:44.482397

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '210ada4775f1'
down_revision: Union[str, Sequence[str], None] = '236f8ebc042e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('telegram_id', sa.Integer(), nullable=True))
    op.create_index('ix_users_telegram_id', 'users', ['telegram_id'], unique=True)

    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
