"""add image_url to models table

Revision ID: f339c48b6368
Revises: c3af29bd0ec0
Create Date: 2025-08-03 11:43:20.625473

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f339c48b6368'
down_revision: Union[str, Sequence[str], None] = 'c3af29bd0ec0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### Оставляем только команду для добавления одной нужной колонки ###
    op.add_column('models', sa.Column('image_url', sa.String(length=512), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### Оставляем только команду для удаления этой же колонки ###
    op.drop_column('models', 'image_url')
    # ### end Alembic commands ###