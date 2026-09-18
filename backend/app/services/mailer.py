from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


def mailer_configured() -> bool:
    return settings.smtp_configured


def send_email(to: str, subject: str, body: str) -> None:
    if not mailer_configured():
        raise RuntimeError("Email is not configured on this server")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from.strip()
    message["To"] = to.strip()
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host.strip(), settings.smtp_port, timeout=20) as client:
        if settings.smtp_use_tls:
            client.starttls()
        if settings.smtp_user.strip():
            client.login(settings.smtp_user.strip(), settings.smtp_password)
        client.send_message(message)
    logger.info("sent email to_host=%s", (to or "").rsplit("@", 1)[-1])
