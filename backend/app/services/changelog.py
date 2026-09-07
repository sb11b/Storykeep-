from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import ChangeLog


def record(
    db: Session,
    user_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    payload: dict[str, Any] | None = None,
) -> None:
    db.add(
        ChangeLog(
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            payload=payload,
        )
    )
