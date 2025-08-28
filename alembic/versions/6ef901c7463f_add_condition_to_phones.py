"""Add condition to phones

Revision ID: 6ef901c7463f
Revises: dfd9b96deb27
Create Date: 2025-08-28 12:25:04.236675

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6ef901c7463f'
down_revision: Union[str, Sequence[str], None] = 'dfd9b96deb27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'phones', 
        sa.Column(
            'condition', 
            sa.Enum('NEW', 'USED', 'REFURBISHED', name='phonecondition', native_enum=False, length=15), # <--- ДОБАВЛЕНО length=15
            server_default='Восстановленный', 
            nullable=False
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('phones', 'condition')