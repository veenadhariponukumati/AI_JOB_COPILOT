"""Minimal transactional email helper using the Resend HTTP API."""

import httpx

from src.core.config import get_settings
from src.core.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

RESEND_API_URL = "https://api.resend.com/emails"


def send_email(to: str, subject: str, html: str) -> None:
    """Send an email via Resend. Logs and swallows failures - email delivery
    should never break the caller's main request flow."""
    if not settings.RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set - skipping email send")
        return
    try:
        response = httpx.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json={
                "from": settings.RESEND_FROM_EMAIL,
                "to": [to],
                "subject": subject,
                "html": html,
            },
            timeout=10,
        )
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to send email to {to}: {e}")
