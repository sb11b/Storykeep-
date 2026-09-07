from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import create_access_token, hash_password, verify_password
from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import LoginIn, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        "sk_access",
        token,
        httponly=True,
        samesite="lax",
        max_age=settings.access_token_minutes * 60,
        path="/",
    )


@router.post("/register", response_model=TokenOut)
def register(payload: RegisterIn, response: Response, db: Session = Depends(get_db)) -> TokenOut:
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name or email.split("@")[0],
        preferences={"theme": "paper", "items_per_page": 40, "mark_read_on_open": True},
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id)
    _set_cookie(response, token)
    return TokenOut(user=UserOut.model_validate(user), access_token=token)


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)) -> TokenOut:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    token = create_access_token(user.id)
    _set_cookie(response, token)
    return TokenOut(user=UserOut.model_validate(user), access_token=token)


@router.post("/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie("sk_access", path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
