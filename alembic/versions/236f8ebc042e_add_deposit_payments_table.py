"""Add deposit payments table

Revision ID: 236f8ebc042e
Revises: 56e4067a2dd4
Create Date: 2025-08-14 23:36:23.003743

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '236f8ebc042e'
down_revision: Union[str, Sequence[str], None] = '56e4067a2dd4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Создаем новую таблицу для хранения платежей по вкладам.
    op.create_table('deposit_payments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('deposit_id', sa.Integer(), nullable=False),
        sa.Column('payment_date', sa.DateTime(), nullable=False),
        sa.Column('amount', sa.Numeric(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
        sa.ForeignKeyConstraint(['deposit_id'], ['deposits.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    # При откате миграции удаляем созданную таблицу.
    op.drop_table('deposit_payments')