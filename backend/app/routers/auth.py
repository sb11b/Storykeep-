from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import create_access_token, hash_password, verify_password
from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import (
    ChangeEmailConfirmIn,
    ChangeEmailRequestIn,
    ChangePasswordIn,
    LoginIn,
    LoginResponseOut,
    MePatchIn,
    ProfileOut,
    ProfilePatchIn,
    RegisterIn,
    TokenOut,
    TotpConfirmIn,
    TotpConfirmOut,
    TotpSetupOut,
    TwoFactorStatusOut,
    TwoFactorVerifyIn,
)
from app.services import auth_challenges, totp_service
from app.services.demo_lock import (
    email_is_locked,
    is_locked,
    profile_is_read_only,
    reject_authentication,
    reject_profile_mutation,
    user_requires_2fa,
)
from app.services.mailer import mailer_configured
from app.services.user_profile import merge_appearance_preferences, profile_out, set_avatar_media, user_out

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_cookie(response: Response, token: str) -> None:
    # Session cookie: HttpOnly + Secure (production) + SameSite=Lax. Fail closed.
    response.set_cookie(
        "sk_access",
        token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.access_token_minutes * 60,
        path="/",
    )


def _issue_login(response: Response, user: User) -> LoginResponseOut:
    token = create_access_token(user.id)
    _set_cookie(response, token)
    return LoginResponseOut(user=user_out(user), access_token=token)


def _pending_totp_secret(user: User) -> str | None:
    encrypted = (user.preferences or {}).get("totp_setup_secret_enc")
    if not encrypted:
        return None
    return totp_service.decrypt_totp_secret(str(encrypted))


def _set_pending_totp_secret(user: User, secret: str) -> None:
    prefs = deepcopy(user.preferences or {})
    prefs["totp_setup_secret_enc"] = totp_service.encrypt_totp_secret(secret)
    user.preferences = prefs


def _clear_pending_totp_secret(user: User) -> None:
    prefs = deepcopy(user.preferences or {})
    prefs.pop("totp_setup_secret_enc", None)
    user.preferences = prefs


@router.post("/register", response_model=TokenOut)
def register(payload: RegisterIn, response: Response, db: Session = Depends(get_db)) -> TokenOut:
    email = payload.email.lower()
    if email_is_locked(email):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Demo account closed")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    if payload.display_name is not None:
        display_name = (payload.display_name or "").strip()[:120] or None
    else:
        display_name = email.split("@")[0]
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        display_name=display_name,
        preferences={"theme": "paper", "items_per_page": 40, "mark_read_on_open": True},
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id)
    _set_cookie(response, token)
    return TokenOut(user=user_out(user), access_token=token)


@router.post("/login", response_model=LoginResponseOut)
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)) -> LoginResponseOut:
    email = payload.email.lower()
    if email_is_locked(email):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Demo account closed")
    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    reject_authentication(user)
    if user_requires_2fa(user):
        challenge = auth_challenges.create_login_challenge(db, user)
        db.commit()
        return LoginResponseOut(
            requires_2fa=True,
            challenge_id=challenge.id,
            totp_available=bool(user.totp_enabled),
            email_otp_available=bool(user.email_otp_enabled and mailer_configured() and challenge.code_hash),
        )
    return _issue_login(response, user)


@router.post("/login/2fa", response_model=LoginResponseOut)
def login_two_factor(payload: TwoFactorVerifyIn, response: Response, db: Session = Depends(get_db)) -> LoginResponseOut:
    challenge = auth_challenges._load_challenge(db, payload.challenge_id, kind="login_2fa")
    user = db.get(User, challenge.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Sign-in challenge expired or invalid")
    verified = False
    if payload.use_backup_code:
        index = totp_service.verify_backup_code(payload.code, list(user.backup_code_hashes or []))
        if index is None:
            raise HTTPException(status_code=401, detail="Invalid backup code")
        hashes = list(user.backup_code_hashes or [])
        hashes.pop(index)
        user.backup_code_hashes = hashes
        verified = True
    elif user.totp_enabled:
        secret = totp_service.decrypt_totp_secret(user.totp_secret_encrypted)
        if secret and totp_service.verify_totp_code(secret, payload.code):
            verified = True
    if not verified and user.email_otp_enabled and challenge.code_hash:
        verified = auth_challenges.verify_login_email_code(db, challenge, payload.code)
    if not verified:
        db.commit()
        raise HTTPException(status_code=401, detail="Incorrect verification code")
    auth_challenges.consume_login_challenge(db, payload.challenge_id)
    db.commit()
    db.refresh(user)
    reject_authentication(user)
    return _issue_login(response, user)


@router.post("/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie("sk_access", path="/", secure=settings.cookie_secure, samesite="lax")
    return {"ok": True}


@router.get("/me", response_model=ProfileOut)
def get_me(user: User = Depends(get_current_user)) -> ProfileOut:
    return profile_out(user)


def _apply_me_patch(db: Session, user: User, payload: MePatchIn) -> None:
    fields = payload.model_fields_set
    if "display_name" in fields:
        user.display_name = (payload.display_name or "").strip()[:120] or None
    if "legal_name" in fields:
        user.legal_name = (payload.legal_name or "").strip()[:120] or None
    if "school_name" in fields:
        user.school_name = (payload.school_name or "").strip()[:120] or None
    if "birthdate" in fields:
        user.birthdate = payload.birthdate
    if "avatar_media_id" in fields:
        set_avatar_media(db, user, payload.avatar_media_id)
    if "appearance" in fields and payload.appearance is not None:
        user.preferences = merge_appearance_preferences(
            user.preferences or {},
            payload.appearance.model_dump(exclude_none=True),
        )


@router.patch("/me", response_model=ProfileOut)
def patch_me(
    payload: MePatchIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProfileOut:
    reject_profile_mutation(user)
    _apply_me_patch(db, user, payload)
    user.updated_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()
    db.refresh(user)
    return profile_out(user)


@router.get("/profile", response_model=ProfileOut)
def get_profile(user: User = Depends(get_current_user)) -> ProfileOut:
    return profile_out(user)


@router.patch("/profile", response_model=ProfileOut)
def patch_profile(
    payload: ProfilePatchIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProfileOut:
    reject_profile_mutation(user)
    _apply_me_patch(db, user, MePatchIn(**payload.model_dump(exclude_unset=True)))
    user.updated_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()
    db.refresh(user)
    return profile_out(user)


@router.post("/change-password")
def change_password(
    payload: ChangePasswordIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, bool]:
    reject_profile_mutation(user)
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    user.updated_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()
    return {"ok": True}


@router.post("/change-email/request")
def change_email_request(
    payload: ChangeEmailRequestIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, bool]:
    reject_profile_mutation(user)
    new_email = payload.new_email.strip().lower()
    if new_email == user.email.lower():
        raise HTTPException(status_code=400, detail="That is already your email address")
    if email_is_locked(new_email):
        raise HTTPException(status_code=400, detail="That email address cannot be used")
    if db.scalar(select(User).where(User.email == new_email)):
        raise HTTPException(status_code=409, detail="Email already registered")
    auth_challenges.create_email_change_challenge(db, user, new_email)
    db.commit()
    return {"ok": True}


@router.post("/change-email/confirm", response_model=ProfileOut)
def change_email_confirm(
    payload: ChangeEmailConfirmIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProfileOut:
    reject_profile_mutation(user)
    new_email = auth_challenges.verify_email_change_code(db, user, payload.code)
    if db.scalar(select(User).where(User.email == new_email)):
        raise HTTPException(status_code=409, detail="Email already registered")
    user.email = new_email
    user.updated_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()
    db.refresh(user)
    return profile_out(user)


@router.get("/2fa", response_model=TwoFactorStatusOut)
def two_factor_status(user: User = Depends(get_current_user)) -> TwoFactorStatusOut:
    return TwoFactorStatusOut(
        totp_enabled=bool(user.totp_enabled),
        email_otp_enabled=bool(user.email_otp_enabled),
        email_otp_available=mailer_configured(),
        has_backup_codes=bool(user.backup_code_hashes),
    )


@router.post("/2fa/totp/setup", response_model=TotpSetupOut)
def setup_totp(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> TotpSetupOut:
    reject_profile_mutation(user)
    if user.totp_enabled:
        raise HTTPException(status_code=400, detail="Authenticator app is already enabled")
    secret = totp_service.generate_totp_secret()
    _set_pending_totp_secret(user, secret)
    user.updated_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()
    uri = totp_service.provisioning_uri(secret, user.email)
    return TotpSetupOut(
        secret=secret,
        otpauth_uri=uri,
        qr_code_data_url=totp_service.qr_code_data_url(uri),
    )


@router.post("/2fa/totp/confirm", response_model=TotpConfirmOut)
def confirm_totp(
    payload: TotpConfirmIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TotpConfirmOut:
    reject_profile_mutation(user)
    secret = _pending_totp_secret(user)
    if not secret:
        raise HTTPException(status_code=400, detail="Start authenticator setup first")
    if not totp_service.verify_totp_code(secret, payload.code):
        raise HTTPException(status_code=400, detail="Incorrect authenticator code")
    backup_codes = totp_service.generate_backup_codes()
    user.totp_secret_encrypted = totp_service.encrypt_totp_secret(secret)
    user.totp_enabled = True
    user.backup_code_hashes = totp_service.hash_backup_codes(backup_codes)
    _clear_pending_totp_secret(user)
    user.updated_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()
    return TotpConfirmOut(backup_codes=backup_codes)


@router.post("/2fa/totp/disable")
def disable_totp(
    payload: TotpConfirmIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, bool]:
    reject_profile_mutation(user)
    if not user.totp_enabled:
        return {"ok": True}
    secret = totp_service.decrypt_totp_secret(user.totp_secret_encrypted)
    if not secret or not totp_service.verify_totp_code(secret, payload.code):
        raise HTTPException(status_code=400, detail="Incorrect authenticator code")
    user.totp_enabled = False
    user.totp_secret_encrypted = None
    _clear_pending_totp_secret(user)
    if not user.email_otp_enabled:
        user.backup_code_hashes = []
    user.updated_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()
    return {"ok": True}


@router.post("/2fa/email/enable")
def enable_email_otp(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, bool]:
    reject_profile_mutation(user)
    if not mailer_configured():
        raise HTTPException(status_code=503, detail="Email codes are not available on this server")
    user.email_otp_enabled = True
    user.updated_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()
    return {"ok": True}


@router.post("/2fa/email/disable")
def disable_email_otp(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, bool]:
    reject_profile_mutation(user)
    user.email_otp_enabled = False
    if not user.totp_enabled:
        user.backup_code_hashes = []
    user.updated_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()
    return {"ok": True}
