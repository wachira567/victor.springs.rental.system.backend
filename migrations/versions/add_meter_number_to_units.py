"""add meter_number to units

Revision ID: add_meter_number_to_units
Revises: a1b2c3d4e5f6
Create Date: 2026-03-31 10:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_meter_number_to_units'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if column already exists
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('units')]
    if 'meter_number' not in columns:
        op.add_column('units', sa.Column('meter_number', sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column('units', 'meter_number')
