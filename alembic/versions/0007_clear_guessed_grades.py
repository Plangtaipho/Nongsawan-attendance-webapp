"""Clear subject grade levels that 0006 filled in by guessing from the code.

The school wants every grade set by hand. A grade that differs from the old
guess was set by a person, so it is kept.

Revision ID: 0007
Revises: 0006
"""
import re

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _old_guess(code: str) -> str | None:
    m = re.fullmatch(r"\D([23])([1-3])\d{3}", (code or "").strip())
    return f"ม.{int(m.group(2)) + (3 if m.group(1) == '3' else 0)}" if m else None


def upgrade() -> None:
    if op.get_context().as_sql:
        return  # data fix needs a live connection
    subjects = sa.table("subjects", sa.column("id", sa.Integer), sa.column("subject_code", sa.String), sa.column("grade_level", sa.String))
    bind = op.get_bind()
    for sid, code, grade in bind.execute(sa.select(subjects.c.id, subjects.c.subject_code, subjects.c.grade_level)).all():
        if grade and grade == _old_guess(code):
            bind.execute(subjects.update().where(subjects.c.id == sid).values(grade_level=None))


def downgrade() -> None:
    pass
