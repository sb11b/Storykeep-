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


def user_from_access_token(db: Session, token: str) -> User:
    """Resolve a raw access token to its user.

    Single verification path shared by HTTP requests (bearer header or
    cookie, via `get_current_user`) and the STT WebSocket, which cannot set
    an Authorization header and therefore passes the token as a query
    parameter fallback when the cookie is absent (see `routers/stt.py`).
    """
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


def token_from_headers(
    authorization: str | None,
    sk_access: str | None,
) -> str | None:
    """Bearer header first (case-insensitive), cookie as fallback."""
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    if sk_access:
        return sk_access
    return None


def get_current_user(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    sk_access: str | None = Cookie(default=None),
) -> User:
    token = token_from_headers(authorization, sk_access)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user_from_access_token(db, token)


def require_user(user: User = Depends(get_current_user)) -> User:
    """Authenticated owner session for Junior. Fail closed — no demo, no anonymous."""
    reject_locked(user)
    return user
