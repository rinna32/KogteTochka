"""windows: запись на окна, которые открывает мастер

Запись теперь привязана к окну, а не к произвольному интервалу времени.
Вместо no_overlap — одна активная запись на окно.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-24 17:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('windows',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('start_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('label', sa.String(length=20), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('start_at')
    )

    op.execute("ALTER TABLE bookings DROP CONSTRAINT no_overlap")
    op.drop_constraint('booking_interval', 'bookings', type_='check')
    op.drop_column('bookings', 'start_at')
    op.drop_column('bookings', 'end_at')
    op.drop_column('bookings', 'nail_length')
    op.drop_column('bookings', 'nail_shape')
    op.alter_column('bookings', 'phone', nullable=True)
    op.alter_column('bookings', 'service_id', nullable=True)
    op.add_column('bookings', sa.Column('client_username', sa.String(length=64), nullable=True))
    op.add_column('bookings', sa.Column('window_id', sa.Integer(), nullable=False))
    op.create_foreign_key(
        'bookings_window_id_fkey', 'bookings', 'windows', ['window_id'], ['id'], ondelete='CASCADE'
    )
    op.create_index(
        'one_active_booking_per_window', 'bookings', ['window_id'],
        unique=True, postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    # Записи на окна в старую схему не переносятся
    op.execute("DELETE FROM bookings")
    op.drop_index('one_active_booking_per_window', table_name='bookings')
    op.drop_constraint('bookings_window_id_fkey', 'bookings', type_='foreignkey')
    op.drop_column('bookings', 'window_id')
    op.drop_column('bookings', 'client_username')
    op.alter_column('bookings', 'service_id', nullable=False)
    op.alter_column('bookings', 'phone', nullable=False)
    op.add_column('bookings', sa.Column('nail_shape', sa.String(length=50), nullable=False))
    op.add_column('bookings', sa.Column('nail_length', sa.String(length=50), nullable=False))
    op.add_column('bookings', sa.Column('end_at', sa.DateTime(timezone=True), nullable=False))
    op.add_column('bookings', sa.Column('start_at', sa.DateTime(timezone=True), nullable=False))
    op.create_check_constraint('booking_interval', 'bookings', 'end_at > start_at')
    op.execute(
        """
        ALTER TABLE bookings ADD CONSTRAINT no_overlap
            EXCLUDE USING gist (tstzrange(start_at, end_at) WITH &&)
            WHERE (status = 'active')
        """
    )
    op.drop_table('windows')
