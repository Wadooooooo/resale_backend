"""Add SPISAN_POSTAVSCHIKOM status to CommerceStatus

Revision ID: b1fcd0b6f49d
Revises: eabb6705ef0f
Create Date: 2025-08-01 23:45:06.086145

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1fcd0b6f49d'
down_revision: Union[str, Sequence[str], None] = 'eabb6705ef0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### НАЧАЛО ИСПРАВЛЕНИЯ ###
    # Alembic изменяет существующий столбец, добавляя новое значение в ENUM
    op.alter_column('phones', 'commercial_status',
               existing_type=sa.Enum('НЕ_ГОТОВ_К_ПРОДАЖЕ', 'НА_СКЛАДЕ', 'ПРОДАН', 'ВОЗВРАТ', 'ГАРАНТИЙНЫЙ_РЕМОНТ', 'ОТПРАВЛЕН_ПОСТАВЩИКУ', name='commercestatus', native_enum=False),
               type_=sa.Enum('НЕ_ГОТОВ_К_ПРОДАЖЕ', 'НА_СКЛАДЕ', 'ПРОДАН', 'ВОЗВРАТ', 'ГАРАНТИЙНЫЙ_РЕМОНТ', 'ОТПРАВЛЕН_ПОСТАВЩИКУ', 'СПИСАН_ПОСТАВЩИКОМ', name='commercestatus', native_enum=False),
               existing_nullable=True)
    # ### КОНЕЦ ИСПРАВЛЕНИЯ ###


def downgrade() -> None:
    # ### НАЧАЛО ИСПРАВЛЕНИЯ ###
    # Откат происходит в обратном порядке
    op.alter_column('phones', 'commercial_status',
               existing_type=sa.Enum('НЕ_ГОТОВ_К_ПРОДАЖЕ', 'НА_СКЛАДЕ', 'ПРОДАН', 'ВОЗВРАТ', 'ГАРАНТИЙНЫЙ_РЕМОНТ', 'ОТПРАВЛЕН_ПОСТАВЩИКУ', 'СПИСАН_ПОСТАВЩИКОМ', name='commercestatus', native_enum=False),
               type_=sa.Enum('НЕ_ГОТОВ_К_ПРОДАЖЕ', 'НА_СКЛАДЕ', 'ПРОДАН', 'ВОЗВРАТ', 'ГАРАНТИЙНЫЙ_РЕМОНТ', 'ОТПРАВЛЕН_ПОСТАВЩИКУ', name='commercestatus', native_enum=False),
               existing_nullable=True)
    # ### КОНЕЦ ИСПРАВЛЕНИЯ ###