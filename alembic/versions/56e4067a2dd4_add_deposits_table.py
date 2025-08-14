"""Add deposits table

Revision ID: 56e4067a2dd4
Revises: ead99ab92dc9
Create Date: 2025-08-14 23:06:19.791215

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '56e4067a2dd4'
down_revision: Union[str, Sequence[str], None] = 'ead99ab92dc9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Создаем новую таблицу 'deposits' для учета вкладов
    op.create_table('deposits',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('lender_name', sa.String(length=255), nullable=False),
        sa.Column('principal_amount', sa.Numeric(), nullable=False),
        sa.Column('annual_interest_rate', sa.Numeric(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Удаляем таблицу 'deposits' при откате миграции
    op.drop_table('deposits')
