from __future__ import annotations

import io
import secrets
import string

import pyotp
import qrcode

from app.auth import hash_password, verify_password
from app.services.crypto_box import decrypt_secret, encrypt_secret


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def encrypt_totp_secret(secret: str) -> str:
    return encrypt_secret(secret)


def decrypt_totp_secret(encrypted: str | None) -> str | None:
    if not encrypted:
        return None
    return decrypt_secret(encrypted)


def provisioning_uri(secret: str, email: str, issuer: str = "Storykeep") -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def qr_code_data_url(uri: str) -> str:
    image = qrcode.make(uri)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    import base64

    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def verify_totp_code(secret: str, code: str) -> bool:
    normalized = (code or "").strip().replace(" ", "")
    if not normalized.isdigit() or len(normalized) != 6:
        return False
    return bool(pyotp.TOTP(secret).verify(normalized, valid_window=1))


def generate_backup_codes(count: int = 10) -> list[str]:
    alphabet = string.ascii_uppercase + string.digits
    codes: list[str] = []
    seen: set[str] = set()
    while len(codes) < count:
        raw = "".join(secrets.choice(alphabet) for _ in range(8))
        code = f"{raw[:4]}-{raw[4:]}"
        if code in seen:
            continue
        seen.add(code)
        codes.append(code)
    return codes


def hash_backup_codes(codes: list[str]) -> list[str]:
    return [hash_password(code) for code in codes]


def verify_backup_code(code: str, hashes: list[str]) -> int | None:
    normalized = (code or "").strip().upper().replace(" ", "")
    if len(normalized) == 8 and "-" not in normalized:
        normalized = f"{normalized[:4]}-{normalized[4:]}"
    for index, stored in enumerate(hashes):
        if verify_password(normalized, stored):
            return index
    return None
