"""Update enum with values_callable

Revision ID: 1b2f7727583a
Revises: 2825d71fcc6d
Create Date: 2025-08-31 01:14:48.728758

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1b2f7727583a'
down_revision: Union[str, Sequence[str], None] = '2825d71fcc6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Не требует изменений в схеме базы данных."""
    pass


def downgrade() -> None:
    """Не требует изменений в схеме базы данных."""
    pass