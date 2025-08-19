"""add_view_to_operation_categories

Revision ID: 043dd525de86
Revises: e7759daee083
Create Date: 2025-08-19 12:00:11.810267

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '043dd525de86'
down_revision: Union[str, Sequence[str], None] = 'e7759daee083'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('operation_categories', sa.Column('view', sa.String(length=50), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    pass
