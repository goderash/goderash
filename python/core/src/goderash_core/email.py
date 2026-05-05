"""Transactional email sending.

Uses stdlib smtplib via a thread-pool executor so the event loop isn't blocked.
If smtp_host is not configured, the email is logged at INFO level (dev mode).
"""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage

import structlog

log = structlog.get_logger()


async def send_email(*, to: str, subject: str, body: str) -> None:
    """Send a plain-text email. Fire-and-forget safe: exceptions are logged, not raised."""
    from .config import get_settings

    s = get_settings()
    if not s.smtp_host:
        log.info(
            "email.noop",
            to=to,
            subject=subject,
            preview=body[:120].replace("\n", " "),
        )
        return

    msg = EmailMessage()
    msg["From"] = s.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _send_sync, msg, s)
    except Exception:
        log.exception("email.send_failed", to=to, subject=subject)


def _send_sync(msg: EmailMessage, settings) -> None:
    ctx = ssl.create_default_context()
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ctx)
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password or "")
        smtp.send_message(msg)
