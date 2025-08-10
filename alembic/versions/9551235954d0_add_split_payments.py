"""add_split_payments

Revision ID: 9551235954d0
Revises: de5190a843f1
Create Date: 2025-08-10 19:06:25.679269

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9551235954d0'
down_revision: Union[str, Sequence[str], None] = 'de5190a843f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Определяем Enum типы заранее для переиспользования
status_pay_enum = sa.Enum('ОЖИДАНИЕ_ОПЛАТЫ', 'ЧАСТИЧНО_ОПЛАЧЕН', 'ОПЛАЧЕН', 'ОТМЕНА', name='statuspay')
payment_method_enum = sa.Enum('НАЛИЧНЫЕ', 'КАРТА', 'КРЕДИТ_РАССРОЧКА', 'ПЕРЕВОД', 'КРИПТОВАЛЮТА', name='enumpayment')


def upgrade() -> None:
    """Upgrade schema."""
    # ### Создаем новую таблицу для хранения платежей ###
    op.create_table('sale_payments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('sale_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(), nullable=False),
        sa.Column('payment_method', payment_method_enum, nullable=False),
        sa.Column('payment_date', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
        sa.ForeignKeyConstraint(['sale_id'], ['sales.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # VVV ГЛАВНОЕ ИСПРАВЛЕНИЕ VVV
    # 1. СНАЧАЛА создаем новый тип Enum в PostgreSQL
    status_pay_enum.create(op.get_bind())

    # 2. ПОТОМ обновляем колонку для его использования
    op.alter_column('sales', 'payment_status',
               existing_type=sa.VARCHAR(length=15),
               type_=status_pay_enum,
               existing_nullable=True,
               postgresql_using='payment_status::text::statuspay'
    )
    
    # ### Удаляем старые колонки из таблицы sales ###
    op.drop_constraint('sales_account_id_fkey', 'sales', type_='foreignkey')
    op.drop_column('sales', 'account_id')
    op.drop_column('sales', 'payment_method')


def downgrade() -> None:
    """Downgrade schema."""
    # ### Возвращаем старые колонки в таблицу sales ###
    op.add_column('sales', sa.Column('payment_method', sa.VARCHAR(length=16), autoincrement=False, nullable=True))
    op.add_column('sales', sa.Column('account_id', sa.INTEGER(), autoincrement=False, nullable=True))
    op.create_foreign_key('sales_account_id_fkey', 'sales', 'accounts', ['account_id'], ['id'])
    
    # ### Возвращаем старый тип данных для статуса оплаты ###
    op.alter_column('sales', 'payment_status',
               type_=sa.VARCHAR(length=15),
               existing_nullable=True
    )
    
    # ### Удаляем новую таблицу с платежами ###
    op.drop_table('sale_payments')

    # ### Удаляем тип Enum при откате миграции ###
    status_pay_enum.drop(op.get_bind())