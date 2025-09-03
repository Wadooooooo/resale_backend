"""Add goods_sent_to_customer_value to financial_snapshots

Revision ID: aebe9ecf0297
Revises: 1b2f7727583a
Create Date: 2025-09-04 00:37:38.250332

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aebe9ecf0297'
down_revision: Union[str, Sequence[str], None] = '1b2f7727583a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'financial_snapshots', 
        sa.Column('goods_sent_to_customer_value', sa.Numeric(), server_default=sa.text('0'), nullable=False)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('financial_snapshots', 'goods_sent_to_customer_value')