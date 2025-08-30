"""Set correct length for non-native enums

Revision ID: 2825d71fcc6d
Revises: 6ef901c7463f
Create Date: 2025-08-31 01:00:15.590735

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2825d71fcc6d'
down_revision: Union[str, Sequence[str], None] = '6ef901c7463f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Применяет изменения к базе данных."""
    # 1. Главное исправление: Меняем тип колонки 'condition' и задаем ей правильную длину (20).
    # Это решает вашу ошибку "value too long for type character varying(11)".
    op.alter_column('phones', 'condition',
               existing_type=sa.VARCHAR(length=15),
               type_=sa.Enum('NEW', 'USED', 'REFURBISHED', name='phonecondition', native_enum=False, length=20),
               existing_nullable=False,
               existing_server_default=sa.text("'Восстановленный'::character varying"))

    # 2. Аналогичное исправление для колонки 'payment_status' в таблице 'repairs'.
    op.alter_column('repairs', 'payment_status',
               existing_type=sa.VARCHAR(length=15),
               type_=sa.Enum('ОЖИДАНИЕ_ОПЛАТЫ', 'ЧАСТИЧНО_ОПЛАЧЕН', 'ОПЛАЧЕН', 'ОТМЕНА', name='statuspay', native_enum=False),
               existing_nullable=True)

    # 3. Аналогичное исправление для колонки 'payment_status' в таблице 'sales'.
    op.alter_column('sales', 'payment_status',
               existing_type=postgresql.ENUM('ОЖИДАНИЕ_ОПЛАТЫ', 'ЧАСТИЧНО_ОПЛАЧЕН', 'ОПЛАЧЕН', 'ОТМЕНА', name='statuspay'),
               type_=sa.Enum('ОЖИДАНИЕ_ОПЛАТЫ', 'ЧАСТИЧНО_ОПЛАЧЕН', 'ОПЛАЧЕН', 'ОТМЕНА', name='statuspay', native_enum=False),
               existing_nullable=True)


def downgrade() -> None:
    """Откатывает изменения."""
    op.alter_column('sales', 'payment_status',
               existing_type=sa.Enum('ОЖИДАНИЕ_ОПЛАТЫ', 'ЧАСТИЧНО_ОПЛАЧЕН', 'ОПЛАЧЕН', 'ОТМЕНА', name='statuspay', native_enum=False),
               type_=postgresql.ENUM('ОЖИДАНИЕ_ОПЛАТЫ', 'ЧАСТИЧНО_ОПЛАЧЕН', 'ОПЛАЧЕН', 'ОТМЕНА', name='statuspay'),
               existing_nullable=True)
    op.alter_column('repairs', 'payment_status',
               existing_type=sa.Enum('ОЖИДАНИЕ_ОПЛАТЫ', 'ЧАСТИЧНО_ОПЛАЧЕН', 'ОПЛАЧЕН', 'ОТМЕНА', name='statuspay', native_enum=False),
               type_=sa.VARCHAR(length=15),
               existing_nullable=True)
    op.alter_column('phones', 'condition',
               existing_type=sa.Enum('NEW', 'USED', 'REFURBISHED', name='phonecondition', native_enum=False, length=20),
               type_=sa.VARCHAR(length=15),
               existing_nullable=False,
               existing_server_default=sa.text("'Восстановленный'::character varying"))