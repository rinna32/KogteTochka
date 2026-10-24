"""no_overlap: две активные записи не могут пересекаться по времени

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-24 16:30:00

"""
from typing import Sequence, Union

from alembic import op


revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        """
        ALTER TABLE bookings ADD CONSTRAINT no_overlap
            EXCLUDE USING gist (tstzrange(start_at, end_at) WITH &&)
            WHERE (status = 'active')
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE bookings DROP CONSTRAINT no_overlap")
