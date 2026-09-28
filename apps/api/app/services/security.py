from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time
import logging
from collections import defaultdict, deque
from typing import Deque

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.models.models import LinkedInConnection


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
logger = logging.getLogger(__name__)
SESSION_COOKIE = "__Host-suvacya-session" if settings.is_production else "suvacya-session"
CSRF_COOKIE = "__Host-suvacya-csrf" if settings.is_production else "suvacya-csrf"


def _secret_bytes() -> bytes:
    return hashlib.sha256(settings.secret_key.encode("utf-8")).digest()


def _key_material(value: str) -> bytes:
    raw = value.strip()
    try:
        decoded = base64.urlsafe_b64decode(raw.encode("ascii"))
        if len(decoded) == 32:
            return decoded
    except Exception:
        pass
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _encryption_keys() -> list[bytes]:
    configured = settings.linkedin_token_encryption_keys
    values = [item.strip() for item in configured.split(",") if item.strip()]
    if not values:
        values = [settings.secret_key]
    return [_key_material(value) for value in values]


def encrypt_linkedin_token(token: str) -> str:
    from cryptography.fernet import Fernet

    key = base64.urlsafe_b64encode(_encryption_keys()[0])
    return "v1:" + Fernet(key).encrypt(token.encode("utf-8")).decode("ascii")


def decrypt_linkedin_token(value: str) -> tuple[str, bool]:
    if not value.startswith("v1:"):
        return value, False

    from cryptography.fernet import Fernet, InvalidToken

    for material in _encryption_keys():
        try:
            key = base64.urlsafe_b64encode(material)
            return Fernet(key).decrypt(value[3:].encode("ascii")).decode("utf-8"), True
        except InvalidToken:
            continue
    raise ValueError("LinkedIn access token could not be decrypted with the configured key set.")


def csrf_token_for_session(session_token: str) -> str:
    random_value = secrets.token_hex(32)
    message = f"{len(session_token)}!{session_token}!{len(random_value)}!{random_value}"
    mac = hmac.new(_secret_bytes(), message.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{mac}.{random_value}"


def validate_csrf_token(session_token: str, supplied: str | None, cookie_value: str | None) -> bool:
    if not supplied or not cookie_value or not hmac.compare_digest(supplied, cookie_value):
        return False
    parts = supplied.split(".", 1)
    if len(parts) != 2:
        return False
    mac, random_value = parts
    message = f"{len(session_token)}!{session_token}!{len(random_value)}!{random_value}"
    expected = hmac.new(_secret_bytes(), message.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, expected)


def set_session_cookies(response: Response, session_token: str) -> None:
    secure = settings.is_production
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_token,
        max_age=7 * 24 * 60 * 60,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE,
        value=csrf_token_for_session(session_token),
        max_age=7 * 24 * 60 * 60,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def request_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
        if token:
            return token
    return request.cookies.get(SESSION_COOKIE)


class RateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        events = self._events[key]
        cutoff = now - window_seconds
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= limit:
            return False
        events.append(now)
        return True


rate_limiter = RateLimiter()


def client_key(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    return hashlib.sha256(host.encode("utf-8")).hexdigest()[:24]


def endpoint_limit(path: str, method: str) -> tuple[int, int]:
    if path.startswith("/api/auth/linkedin/"):
        return (12, 60)
    if path.startswith("/api/research/"):
        return (12, 60)
    if path.startswith("/api/agent/"):
        return (12, 60)
    if path.startswith("/api/content/"):
        return (20, 60)
    if path.startswith("/api/approvals/"):
        return (30, 60)
    if path.startswith("/api/learning/"):
        return (30, 60)
    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        return (60, 60)
    return (240, 60)


_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")
_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{16,}", re.I)


def minimize_ai_text(value: str) -> str:
    value = _BEARER_RE.sub("[REDACTED_CREDENTIAL]", value)
    value = _EMAIL_RE.sub("[REDACTED_EMAIL]", value)
    value = _PHONE_RE.sub("[REDACTED_PHONE]", value)
    return value


async def migrate_plaintext_linkedin_tokens(session) -> int:
    try:
        result = await session.execute(select(LinkedInConnection))
    except OperationalError as exc:
        if "no such table" in str(exc).lower():
            return 0
        raise
    changed = 0
    for connection in result.scalars().all():
        if connection.access_token and not connection.access_token.startswith("v1:"):
            connection.access_token = encrypt_linkedin_token(connection.access_token)
            changed += 1
    if changed:
        await session.commit()
    return changed


def security_event(event_type: str, request: Request, **fields: object) -> None:
    safe_fields = {key: str(value)[:200] for key, value in fields.items()}
    logger.warning(
        "security_event type=%s path=%s client=%s fields=%s",
        event_type,
        request.url.path,
        client_key(request),
        safe_fields,
    )
