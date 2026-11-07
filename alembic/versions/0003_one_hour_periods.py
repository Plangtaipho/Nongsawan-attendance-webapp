"""Periods of one hour: 1-3 morning, slot 4 lunch, 5-7 afternoon.

Replaces earlier auto-created defaults (from 0001's app release or 0002) only if the
table still holds exactly one of those sets and no attendance uses it.

Revision ID: 0003
Revises: 0002
"""
from datetime import time

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

OLD_V1 = {
    (1, time(8, 40), time(9, 30)), (2, time(9, 30), time(10, 20)), (3, time(10, 20), time(11, 10)),
    (4, time(11, 10), time(12, 0)), (5, time(12, 30), time(13, 20)), (6, time(13, 20), time(14, 10)),
    (7, time(14, 10), time(15, 0)),
}
OLD_V2 = {
    (1, time(8, 40), time(9, 30)), (2, time(9, 30), time(10, 20)), (3, time(10, 20), time(11, 10)),
    (5, time(12, 30), time(13, 20)), (6, time(13, 20), time(14, 10)), (7, time(14, 10), time(15, 0)),
}
NEW = [
    (1, time(8, 40), time(9, 40)), (2, time(9, 40), time(10, 40)), (3, time(10, 40), time(11, 40)),
    (5, time(12, 30), time(13, 30)), (6, time(13, 30), time(14, 30)), (7, time(14, 30), time(15, 30)),
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
    bind = op.get_bind()
    rows = {(r.period_no, _as_time(r.start_time), _as_time(r.end_time)) for r in bind.execute(sa.select(periods))}
    used = bind.execute(sa.select(sa.func.count()).select_from(sessions)).scalar()
    if rows not in (OLD_V1, OLD_V2) or used:
        return
    bind.execute(periods.delete())
    bind.execute(periods.insert(), [{"period_no": n, "start_time": a, "end_time": b} for n, a, b in NEW])


def downgrade() -> None:
    pass  # data-only fix
