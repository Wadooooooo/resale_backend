"""Add employee shifts table

Revision ID: 19d067aea0f5
Revises: ecf330e91490
Create Date: 2025-08-05 12:07:16.285132

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '19d067aea0f5'
down_revision: Union[str, Sequence[str], None] = 'ecf330e91490'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### НАЧАЛО ВАЖНОЙ ЧАСТИ ###
    op.create_table('employee_shifts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('shift_start', sa.DateTime(), nullable=False),
        sa.Column('shift_end', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    # ### КОНЕЦ ВАЖНОЙ ЧАСТИ ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### НАЧАЛО ВАЖНОЙ ЧАСТИ ###
    op.drop_table('employee_shifts')
    # ### КОНЕЦ ВАЖНОЙ ЧАСТИ ###