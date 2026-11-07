"""Replace the first default periods with the school's real day.

The previous release created periods 1-7 with lunch after period 4. The school's
day has lunch as slot 4 (periods 1-3 morning, 5-7 afternoon). Replace the old rows
only if they are exactly the old default and no attendance uses them yet, so
periods an admin entered or already used are never touched.

Revision ID: 0002
Revises: 0001
"""
from datetime import time

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

OLD = {
    (1, time(8, 40), time(9, 30)), (2, time(9, 30), time(10, 20)), (3, time(10, 20), time(11, 10)),
    (4, time(11, 10), time(12, 0)), (5, time(12, 30), time(13, 20)), (6, time(13, 20), time(14, 10)),
    (7, time(14, 10), time(15, 0)),
}
NEW = [
    (1, time(8, 40), time(9, 30)), (2, time(9, 30), time(10, 20)), (3, time(10, 20), time(11, 10)),
    (5, time(12, 30), time(13, 20)), (6, time(13, 20), time(14, 10)), (7, time(14, 10), time(15, 0)),
]

periods = sa.table(
    "periods",
    sa.column("id", sa.Integer), sa.column("period_no", sa.SmallInteger),
    sa.column("start_time", sa.Time), sa.column("end_time", sa.Time),
)
sessions = sa.table("attendance_sessions", sa.column("id", sa.Integer))


def _as_time(v):
    # MySQL drivers return TIME as timedelta; SQLite gives time.
    if hasattr(v, "total_seconds"):
        s = int(v.total_seconds())
        return time(s // 3600, s % 3600 // 60)
    return v


def upgrade() -> None:
    if op.get_context().as_sql:
        return  # data fix needs a live connection; skipped when printing SQL
    bind = op.get_bind()
    rows = {(r.period_no, _as_time(r.start_time), _as_time(r.end_time)) for r in bind.execute(sa.select(periods))}
    used = bind.execute(sa.select(sa.func.count()).select_from(sessions)).scalar()
    if rows != OLD or used:
        return
    bind.execute(periods.delete())
    bind.execute(periods.insert(), [{"period_no": n, "start_time": a, "end_time": b} for n, a, b in NEW])


def downgrade() -> None:
    pass  # data-only fix
