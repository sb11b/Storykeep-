import secrets

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import decode_access_token
from app.config import settings
from app.database import get_db
from app.models import User
from app.seed import OWNER_EMAIL
from app.services.demo_lock import reject_authentication, reject_locked


def get_current_user(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    sk_access: str | None = Cookie(default=None),
) -> User:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    elif sk_access:
        token = sk_access
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if settings.service_token and secrets.compare_digest(token, settings.service_token):
        owner = db.scalar(select(User).where(User.email == OWNER_EMAIL))
        if owner is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Owner account missing")
        reject_authentication(owner)
        return owner
    user = db.get(User, decode_access_token(token))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    reject_authentication(user)
    return user


def require_user(user: User = Depends(get_current_user)) -> User:
    """Authenticated owner session for Junior. Fail closed — no demo, no anonymous."""
    reject_locked(user)
    return user
