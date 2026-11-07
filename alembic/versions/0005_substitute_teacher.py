"""Record who a substitute teacher (สอนแทน) stood in for.

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("attendance_sessions") as batch:
        batch.add_column(sa.Column("substitute_for_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_session_substitute_for", "users", ["substitute_for_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("attendance_sessions") as batch:
        batch.drop_constraint("fk_session_substitute_for", type_="foreignkey")
        batch.drop_column("substitute_for_id")
