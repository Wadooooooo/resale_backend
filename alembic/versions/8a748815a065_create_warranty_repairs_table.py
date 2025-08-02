"""Create warranty_repairs table

Revision ID: 8a748815a065
Revises: b1fcd0b6f49d
Create Date: 2025-08-02 00:24:09.063996

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a748815a065'
down_revision: Union[str, Sequence[str], None] = 'b1fcd0b6f49d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### Оставляем только команду для создания новой таблицы ###
    op.create_table('warranty_repairs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('phone_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('date_accepted', sa.DateTime(), nullable=False),
    sa.Column('customer_name', sa.String(length=255), nullable=False),
    sa.Column('customer_phone', sa.String(length=50), nullable=False),
    sa.Column('problem_description', sa.Text(), nullable=False),
    sa.Column('device_condition', sa.Text(), nullable=False),
    sa.Column('included_items', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('date_returned', sa.DateTime(), nullable=True),
    sa.Column('work_performed', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['phone_id'], ['phones.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### Оставляем только команду для удаления этой же таблицы ###
    op.drop_table('warranty_repairs')
    # ### end Alembic commands ###