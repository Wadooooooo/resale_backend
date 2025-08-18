"""change_telegram_id_to_bigint

Revision ID: e7759daee083
Revises: 491dfdba6c58
Create Date: 2025-08-19 00:46:34.455019

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7759daee083'
down_revision: Union[str, Sequence[str], None] = '491dfdba6c58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('users', 'telegram_id',
           existing_type=sa.INTEGER(),
           type_=sa.BIGINT(),
           existing_nullable=True)

def downgrade() -> None:
    """Downgrade schema."""
    pass
