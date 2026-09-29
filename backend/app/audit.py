from __future__ import annotations

from sqlalchemy.orm import Session

from .models import AuditLog, User


def audit(db: Session, user: User | None, action: str, entity: str | None = None,
          entity_id: object = None, details: dict | None = None, ip: str | None = None,
          username: str | None = None) -> None:
    """Registra ação importante. Faz parte da transação corrente do chamador."""
    db.add(AuditLog(
        user_id=user.id if user else None,
        username=(user.username if user else username),
        action=action, entity=entity,
        entity_id=None if entity_id is None else str(entity_id),
        details=details, ip_address=ip,
    ))
