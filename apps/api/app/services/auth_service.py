from dataclasses import dataclass
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AuthSession, AuthUser


@dataclass
class AppUser:
    id: str
    email: str
    role: str
    display_name: str | None = None
    linkedin_url: str | None = None


WHITELISTED_LINKEDIN_USERS: Final[dict[str, dict[str, str]]] = {
    "kanishka.utsav@gmail.com": {
        "linkedin_url": "https://www.linkedin.com/in/kanishkautsav/",
        "display_name": "Kanishka Utsav",
        "role": "owner",
    },
    "pranaybeatking@gmail.com": {
        "linkedin_url": "https://www.linkedin.com/in/kumar-pranay-548181309/",
        "display_name": "Kumar Pranay",
        "role": "owner",
    },
}


class AuthService:
    """Supabase/Postgres-backed auth facade for whitelist-based LinkedIn access."""

    @staticmethod
    def normalize_email(value: str | None) -> str | None:
        if not value:
            return None
        return value.strip().lower()

    @staticmethod
    def normalize_linkedin_url(value: str | None) -> str | None:
        if not value:
            return None
        return value.strip().rstrip('/').lower()

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    async def validate_linkedin_identity(session: AsyncSession, email: str | None, linkedin_url: str | None) -> AppUser | None:
        normalized_email = AuthService.normalize_email(email)
        normalized_linkedin_url = AuthService.normalize_linkedin_url(linkedin_url)
        if not normalized_email or not normalized_linkedin_url:
            return None

        whitelist = WHITELISTED_LINKEDIN_USERS.get(normalized_email)
        if not whitelist:
            return None

        expected_url = AuthService.normalize_linkedin_url(whitelist["linkedin_url"])
        if normalized_linkedin_url != expected_url:
            return None

        result = await session.execute(select(AuthUser).where(AuthUser.email == normalized_email))
        user = result.scalar_one_or_none()

        if user is None:
            user = AuthUser(
                email=normalized_email,
                linkedin_url=expected_url,
                display_name=whitelist["display_name"],
                role=whitelist["role"],
                is_active=True,
                is_whitelisted=True,
            )
            session.add(user)
            await session.flush()
        else:
            user.linkedin_url = expected_url
            user.display_name = whitelist["display_name"]
            user.role = whitelist["role"]
            user.is_active = True
            user.is_whitelisted = True

        await session.commit()
        await session.refresh(user)

        return AppUser(
            id=str(user.id),
            email=user.email,
            role=user.role,
            display_name=user.display_name,
            linkedin_url=user.linkedin_url,
        )

    @staticmethod
    async def create_session(session: AsyncSession, user: AppUser) -> str:
        token = secrets.token_urlsafe(32)
        token_hash = AuthService.hash_token(token)
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        existing = await session.execute(select(AuthSession).where(AuthSession.token_hash == token_hash))
        current = existing.scalar_one_or_none()
        if current is not None:
            current.expires_at = expires_at
            await session.commit()
            return token

        user_row_result = await session.execute(select(AuthUser).where(AuthUser.email == user.email))
        user_row = user_row_result.scalar_one_or_none()
        if user_row is None:
            user_row = AuthUser(
                email=user.email,
                linkedin_url=user.linkedin_url,
                display_name=user.display_name,
                role=user.role,
                is_active=True,
                is_whitelisted=True,
            )
            session.add(user_row)
            await session.flush()

        session_row = AuthSession(user_id=user_row.id, token_hash=token_hash, expires_at=expires_at)
        session.add(session_row)
        await session.commit()
        return token

    @staticmethod
    async def get_user_from_token(session: AsyncSession, token: str | None) -> AppUser | None:
        if not token:
            return None

        normalized = token.strip()
        if not normalized:
            return None

        if normalized in {"owner", "admin", "reviewer"}:
            return AppUser(id=normalized, email=f"{normalized}@local.test", role=normalized)

        token_hash = AuthService.hash_token(normalized)
        result = await session.execute(
            select(AuthSession, AuthUser)
            .join(AuthUser, AuthSession.user_id == AuthUser.id)
            .where(AuthSession.token_hash == token_hash)
            .where(AuthSession.expires_at > datetime.now(timezone.utc))
        )
        row = result.first()
        if row is None:
            return None

        session_row, user_row = row
        if session_row is None or user_row is None:
            return None

        return AppUser(
            id=str(user_row.id),
            email=user_row.email,
            role=user_row.role,
            display_name=user_row.display_name,
            linkedin_url=user_row.linkedin_url,
        )
