"""Add discount to sales table

Revision ID: c3af29bd0ec0
Revises: 8a748815a065
Create Date: 2025-08-02 01:10:17.010835

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3af29bd0ec0'
down_revision: Union[str, Sequence[str], None] = '8a748815a065'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### Оставляем только одну команду для добавления нужной колонки ###
    op.add_column('sales', sa.Column('discount', sa.Numeric(), nullable=True, server_default='0'))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### Оставляем только одну команду для удаления этой же колонки ###
    op.drop_column('sales', 'discount')
    # ### end Alembic commands ###