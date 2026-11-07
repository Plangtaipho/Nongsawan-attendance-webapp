"""Add grade level (ชั้น) to subjects. The admin sets it; it is never guessed.

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("subjects") as batch:
        batch.add_column(sa.Column("grade_level", sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("subjects") as batch:
        batch.drop_column("grade_level")
