"""Add grade level (ชั้น) to subjects, guessed from standard subject codes.

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op

from app.models import guess_grade_level

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("subjects") as batch:
        batch.add_column(sa.Column("grade_level", sa.String(length=20), nullable=True))
    if op.get_context().as_sql:
        return  # data fill needs a live connection; skipped when printing SQL
    subjects = sa.table("subjects", sa.column("id", sa.Integer), sa.column("subject_code", sa.String), sa.column("grade_level", sa.String))
    bind = op.get_bind()
    for sid, code in bind.execute(sa.select(subjects.c.id, subjects.c.subject_code)).all():
        grade = guess_grade_level(code)
        if grade:
            bind.execute(subjects.update().where(subjects.c.id == sid).values(grade_level=grade))


def downgrade() -> None:
    with op.batch_alter_table("subjects") as batch:
        batch.drop_column("grade_level")
