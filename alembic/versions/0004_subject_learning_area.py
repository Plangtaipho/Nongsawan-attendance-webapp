"""Add learning area (กลุ่มสาระ) to subjects, filled in from the subject code.

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

from app.models import guess_learning_area

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("subjects") as batch:
        batch.add_column(sa.Column("learning_area", sa.String(length=60), nullable=True))
    if op.get_context().as_sql:
        return  # data fix needs a live connection; skipped when printing SQL
    subjects = sa.table("subjects", sa.column("id", sa.Integer), sa.column("subject_code", sa.String), sa.column("learning_area", sa.String))
    bind = op.get_bind()
    for sid, code in bind.execute(sa.select(subjects.c.id, subjects.c.subject_code)).all():
        area = guess_learning_area(code)
        if area:
            bind.execute(subjects.update().where(subjects.c.id == sid).values(learning_area=area))


def downgrade() -> None:
    with op.batch_alter_table("subjects") as batch:
        batch.drop_column("learning_area")
