"""Add cash received and change given to sales

Revision ID: 3050e5dd5d04
Revises: ea678edeec05
Create Date: 2025-08-06 00:04:14.815233

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3050e5dd5d04'
down_revision: Union[str, Sequence[str], None] = 'ea678edeec05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### НАЧАЛО ВАЖНОЙ ЧАСТИ ###
    op.add_column('sales', sa.Column('cash_received', sa.Numeric(), nullable=True))
    op.add_column('sales', sa.Column('change_given', sa.Numeric(), nullable=True))
    # ### КОНЕЦ ВАЖНОЙ ЧАСТИ ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### НАЧАЛО ВАЖНОЙ ЧАСТИ ###
    op.drop_column('sales', 'change_given')
    op.drop_column('sales', 'cash_received')
    # ### КОНЕЦ ВАЖНОЙ ЧАСТИ ###