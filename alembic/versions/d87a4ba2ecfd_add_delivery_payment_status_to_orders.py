"""add_delivery_payment_status_to_orders

Revision ID: d87a4ba2ecfd
Revises: 86e89459d465
Create Date: 2025-08-20 11:48:11.458105

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd87a4ba2ecfd'
down_revision: Union[str, Sequence[str], None] = '86e89459d465'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adds delivery_payment_status column to supplier_orders table."""
    op.add_column(
        'supplier_orders',
        sa.Column(
            'delivery_payment_status',
            sa.Enum('НЕ_ОПЛАЧЕН', 'ЧАСТИЧНО_ОПЛАЧЕН', 'ОПЛАЧЕН', name='orderpaymentstatus', native_enum=False),
            nullable=False,
            # Добавляем значение по умолчанию для существующих строк в таблице
            server_default='НЕ_ОПЛАЧЕН'
        )
    )


def downgrade() -> None:
    """Removes delivery_payment_status column from supplier_orders table."""
    op.drop_column('supplier_orders', 'delivery_payment_status')