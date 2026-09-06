from sqlalchemy.orm import Session
from app.models import AuditLog


def log_action(
    db: Session,
    *,
    user_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    row = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_data=before,
        after_data=after,
        ip_address=ip_address,
    )
    db.add(row)
    return row
