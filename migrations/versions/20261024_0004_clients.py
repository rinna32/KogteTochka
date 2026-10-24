"""clients: все, кто писал боту, — для рассылки «Горит окошко»

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-24 17:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('clients',
    sa.Column('tg_id', sa.BigInteger(), autoincrement=False, nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('username', sa.String(length=64), nullable=True),
    sa.Column('is_blocked', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('tg_id')
    )
    # Те, кто уже записывался, — тоже клиентки
    op.execute(
        """
        INSERT INTO clients (tg_id, name, username)
        SELECT DISTINCT ON (client_tg_id) client_tg_id, client_name, client_username
        FROM bookings
        ORDER BY client_tg_id, created_at DESC
        """
    )


def downgrade() -> None:
    op.drop_table('clients')
