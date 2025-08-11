"""add delivery method to sales

Revision ID: 1b968018e895
Revises: 9551235954d0
Create Date: 2025-08-11 11:20:25.036823

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1b968018e895'
down_revision: Union[str, Sequence[str], None] = '9551235954d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Добавляем новую колонку для способа доставки в таблицу 'sales'.
    op.add_column('sales', sa.Column('delivery_method', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Удаляем колонку, добавленную в upgrade.
    op.drop_column('sales', 'delivery_method')