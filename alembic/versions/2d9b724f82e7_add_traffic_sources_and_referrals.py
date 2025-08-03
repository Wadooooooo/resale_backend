"""add traffic sources and referrals

Revision ID: 2d9b724f82e7
Revises: f339c48b6368
Create Date: 2025-08-03 19:07:18.211353

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2d9b724f82e7'
down_revision: Union[str, Sequence[str], None] = 'f339c48b6368'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### Оставляем только нужные команды ###
    
    # 1. Создаем новую таблицу для источников трафика
    op.create_table('traffic_sources',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    
    # 2. Удаляем старое текстовое поле 'source' из таблицы customers
    # op.drop_column('customers', 'source')
    
    # 3. Добавляем две новые колонки в таблицу customers
    op.add_column('customers', sa.Column('source_id', sa.Integer(), nullable=True))
    op.add_column('customers', sa.Column('referrer_id', sa.Integer(), nullable=True))
    
    # 4. Создаем внешние ключи для новых колонок
    op.create_foreign_key('fk_customers_source_id', 'customers', 'traffic_sources', ['source_id'], ['id'])
    op.create_foreign_key('fk_customers_referrer_id', 'customers', 'customers', ['referrer_id'], ['id'])
    
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### Выполняем действия в обратном порядке для отката ###
    
    # 1. Удаляем внешние ключи
    op.drop_constraint('fk_customers_referrer_id', 'customers', type_='foreignkey')
    op.drop_constraint('fk_customers_source_id', 'customers', type_='foreignkey')
    
    # 2. Удаляем новые колонки
    op.drop_column('customers', 'referrer_id')
    op.drop_column('customers', 'source_id')
    
    # 3. Возвращаем старую колонку 'source'
    op.add_column('customers', sa.Column('source', sa.VARCHAR(length=255), autoincrement=False, nullable=True))

    # 4. Удаляем новую таблицу
    op.drop_table('traffic_sources')
    
    # ### end Alembic commands ###