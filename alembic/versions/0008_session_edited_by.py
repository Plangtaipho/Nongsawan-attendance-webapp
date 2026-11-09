"""Remember who last changed an attendance session, and when.

The recorder (teacher_id) never changes. updated_by_id is whoever saved,
moved or edited it last; edited_at is set on every change after the first
save (UTC), so the history can show "แก้ไขล่าสุดโดย ...".

Revision ID: 0008
Revises: 0007
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("attendance_sessions") as batch:
        batch.add_column(sa.Column("updated_by_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("edited_at", sa.DateTime(), nullable=True))
        batch.create_foreign_key("fk_session_updated_by", "users", ["updated_by_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("attendance_sessions") as batch:
        batch.drop_constraint("fk_session_updated_by", type_="foreignkey")
        batch.drop_column("edited_at")
        batch.drop_column("updated_by_id")
