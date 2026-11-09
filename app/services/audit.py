"""Write audit log rows. The caller commits them together with its own change."""
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog, User


def log(db: Session, user: User, action: str, entity: str, entity_id: int | None, detail: dict[str, Any] | None = None) -> None:
    # created_at is set here in UTC so the audit page can show Thai local time reliably.
    db.add(AuditLog(user_id=user.id, action=action, entity=entity, entity_id=entity_id, detail=detail,
                    created_at=datetime.now(UTC).replace(tzinfo=None)))
