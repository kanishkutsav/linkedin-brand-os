import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import urllib.parse
import base64
import urllib.request
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import AuthUser, LinkedInConnection, LinkedInOAuthExchange, LinkedInOAuthState, UserProfile
from app.services.auth_service import AppUser, AuthService
from app.services.security import encrypt_linkedin_token


logger = logging.getLogger(__name__)

LINKEDIN_AUTHORIZE_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def redirect_uri() -> str:
    # The configured callback is authoritative in every environment. This lets
    # Vercel use the canonical Vercel callback while the Render fallback keeps
    # its own registered callback during the migration period.
    if settings.linkedin_redirect_uri:
        return settings.linkedin_redirect_uri.rstrip("/")
    base = (settings.api_base_url or settings.render_external_url or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=500, detail="API_BASE_URL is not configured")
    return f"{base}/api/auth/linkedin/callback"


def _request_json(url: str, *, data: dict | None = None, headers: dict | None = None, timeout: int = 20) -> dict:
    encoded = urllib.parse.urlencode(data).encode("utf-8") if data is not None else None
    request = urllib.request.Request(
        url,
        data=encoded,
        headers=headers or {},
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LinkedIn API request failed: {exc}") from exc


def _decode_jwt_payload(token: str | None) -> dict:
    if not token or token.count(".") != 2:
        return {}
    try:
        payload = token.split(".", 2)[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
    except Exception:
        return {}


async def build_authorization_url(session: AsyncSession, browser_nonce: str | None = None) -> tuple[str, str]:
    if not settings.linkedin_client_id or not settings.linkedin_client_secret:
        raise HTTPException(
            status_code=503,
            detail="LinkedIn OAuth is not configured. Add LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET in Render.",
        )

    browser_nonce = browser_nonce or secrets.token_urlsafe(32)
    if len(browser_nonce) > 200:
        raise HTTPException(status_code=400, detail="Invalid OAuth browser nonce.")
    random_state = secrets.token_urlsafe(32)
    state = f"{random_state}.{browser_nonce}"
    session.add(
        LinkedInOAuthState(
            state_hash=_hash(state),
            browser_nonce_hash=_hash(browser_nonce),
            expires_at=_utc_now() + timedelta(minutes=10),
        )
    )
    await session.commit()

    # Keep LinkedIn connection on the self-serve OIDC + Share on LinkedIn
    # permissions only. Brand DNA is bootstrapped from the profile data those
    # permissions expose, then reviewed by the user. Historical posts remain
    # optional user-imported evidence because member post-read access is closed.
    scopes = ["openid", "profile", "email", "w_member_social"]
    if settings.linkedin_analytics_oauth_enabled:
        scopes.extend(["r_member_postAnalytics", "r_member_profileAnalytics"])

    params = {
        "response_type": "code",
        "client_id": settings.linkedin_client_id,
        "redirect_uri": redirect_uri(),
        "state": state,
        "scope": " ".join(scopes),
        # Let LinkedIn expose supported extended sign-in options where available.
        "enable_extended_login": "true",
    }
    url = f"{LINKEDIN_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"
    return url, state


async def sync_missing_profile_data(session: AsyncSession, user_id: int) -> dict:
    """Refresh only missing LinkedIn OIDC profile fields for an existing connection.

    This intentionally makes no LinkedIn request when all fields added by the
    profile-sync feature are already present. Existing non-null values are never
    overwritten. A failed refresh is non-fatal because the user may have an
    expired token or LinkedIn may simply not return the optional claim.
    """
    result = await session.execute(
        select(LinkedInConnection).where(LinkedInConnection.user_id == user_id)
    )
    connection = result.scalar_one_or_none()
    if connection is None:
        return {"connected": False, "attempted": False, "updated": False}

    missing_fields = [
        field for field, value in (
            ("headline", connection.linkedin_headline),
            ("picture_url", connection.linkedin_picture_url),
            ("locale", connection.linkedin_locale),
            ("vanity_name", connection.linkedin_vanity_name),
        ) if not value or not str(value).strip()
    ]
    if not missing_fields:
        return {"connected": True, "attempted": False, "updated": False, "missing_fields": []}

    try:
        userinfo = await asyncio.to_thread(
            _request_json,
            LINKEDIN_USERINFO_URL,
            headers={"Authorization": f"Bearer {decrypt_linkedin_token(connection.access_token)[0]}"},
        )
    except HTTPException as exc:
        logger.info("LinkedIn missing-profile sync skipped for user %s: %s", user_id, exc.detail)
        return {
            "connected": True,
            "attempted": True,
            "updated": False,
            "missing_fields": missing_fields,
            "error": "LinkedIn profile refresh was not available",
        }

    profile_data = dict(userinfo or {})
    headline = str(profile_data.get("headline") or profile_data.get("localizedHeadline") or "").strip()[:500] or None
    picture_url = str(profile_data.get("picture") or "").strip() or None
    locale_value = profile_data.get("locale")
    if isinstance(locale_value, dict):
        language = str(locale_value.get("language") or "").strip()
        country = str(locale_value.get("country") or "").strip()
        locale = "-".join(part for part in (language, country) if part)[:30] or None
    else:
        locale = str(locale_value).strip()[:30] if locale_value else None
    vanity_name = str(profile_data.get("vanityName") or "").strip()[:255] or None

    updated_fields: list[str] = []
    for field, value in (
        ("headline", headline),
        ("picture_url", picture_url),
        ("locale", locale),
        ("vanity_name", vanity_name),
    ):
        if not value:
            continue
        attr = "linkedin_" + field
        if not getattr(connection, attr):
            setattr(connection, attr, value)
            updated_fields.append(field)

    if updated_fields:
        connection.linkedin_profile_synced_at = _utc_now()
        await session.commit()

    return {
        "connected": True,
        "attempted": True,
        "updated": bool(updated_fields),
        "updated_fields": updated_fields,
        "missing_fields": missing_fields,
        "profile": {
            "headline": connection.linkedin_headline,
            "picture_url": connection.linkedin_picture_url,
            "locale": connection.linkedin_locale,
            "vanity_name": connection.linkedin_vanity_name,
        },
    }


async def handle_callback(session: AsyncSession, code: str, state: str) -> str:
    """Complete the LinkedIn authorization-code flow without leaving 500s opaque.

    The OAuth state remains reserved until the LinkedIn exchange and local
    persistence both succeed. This prevents a transient downstream failure from
    consuming the browser's only usable authorization transaction.
    """
    state_row = None
    try:
        result = await session.execute(
            select(LinkedInOAuthState).where(
                LinkedInOAuthState.state_hash == _hash(state),
                LinkedInOAuthState.expires_at > _utc_now(),
            )
        )
        state_row = result.scalar_one_or_none()
        if state_row is None:
            raise HTTPException(status_code=400, detail="Invalid or expired LinkedIn OAuth state.")

        browser_nonce_hash = state_row.browser_nonce_hash

        # Exchange the authorization code before mutating local OAuth state.
        # LinkedIn requires the redirect_uri to exactly match the URI used when
        # the authorization code was issued.
        try:
            token_payload = await asyncio.to_thread(
                _request_json,
                LINKEDIN_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": settings.linkedin_client_id,
                    "client_secret": settings.linkedin_client_secret,
                    "redirect_uri": redirect_uri(),
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except HTTPException:
            logger.warning("LinkedIn OAuth token exchange rejected the authorization code")
            raise
        except Exception as exc:
            logger.exception("LinkedIn OAuth token exchange failed type=%s", type(exc).__name__)
            raise HTTPException(status_code=502, detail="LinkedIn token exchange failed.") from exc

        access_token = token_payload.get("access_token")
        if not access_token:
            logger.error("LinkedIn OAuth token response did not contain an access token")
            raise HTTPException(status_code=502, detail="LinkedIn did not return an access token.")

        expires_in = token_payload.get("expires_in")
        try:
            token_expires_at = _utc_now() + timedelta(seconds=int(expires_in)) if expires_in else None
        except (TypeError, ValueError):
            logger.warning("LinkedIn OAuth token response contained an invalid expires_in value")
            token_expires_at = None

        # Keep LinkedIn userinfo as the authoritative member identity source.
        # The ID token is only used as an enrichment source after userinfo succeeds,
        # preserving the existing trust model without treating an unverified JWT
        # payload as an authorization credential.
        try:
            userinfo = await asyncio.to_thread(
                _request_json,
                LINKEDIN_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except HTTPException as exc:
            logger.warning(
                "LinkedIn userinfo request failed status=%s",
                exc.status_code,
            )
            raise HTTPException(
                status_code=502,
                detail="LinkedIn member identity could not be retrieved.",
            ) from exc

        profile_data = dict(userinfo or {})
        oidc_claims = _decode_jwt_payload(token_payload.get("id_token"))
        for key, value in oidc_claims.items():
            if key not in profile_data or not profile_data.get(key):
                profile_data[key] = value

        email = AuthService.normalize_email(profile_data.get("email"))
        member_sub = str(profile_data.get("sub") or "").strip()
        display_name = str(profile_data.get("name") or "LinkedIn Member").strip()[:150] or "LinkedIn Member"

        # LinkedIn OIDC can expose a richer profile payload depending on the
        # provisioned permissions. These fields are optional and never gate auth.
        headline = str(profile_data.get("headline") or profile_data.get("localizedHeadline") or "").strip()[:500] or None
        picture_url = str(profile_data.get("picture") or "").strip() or None
        locale_value = profile_data.get("locale")
        if isinstance(locale_value, dict):
            language = str(locale_value.get("language") or "").strip()
            country = str(locale_value.get("country") or "").strip()
            locale = "-".join(part for part in (language, country) if part)[:30] or None
        else:
            locale = str(locale_value).strip()[:30] if locale_value else None
        vanity_name = str(profile_data.get("vanityName") or "").strip()[:255] or None

        if not email or not member_sub:
            raise HTTPException(status_code=403, detail="LinkedIn did not return the required member identity.")

        # The application database is the authorization source of truth.
        user_result = await session.execute(
            select(AuthUser).where(
                AuthUser.email == email,
                AuthUser.is_active.is_(True),
                AuthUser.is_whitelisted.is_(True),
            )
        )
        user = user_result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=403,
                detail="You are not authorized to use this application. Please contact the administrator.",
            )

        # A LinkedIn member identity can only belong to one application user.
        # Detect the conflict before the INSERT/UPDATE so it never becomes an
        # opaque database 500.
        connection_result = await session.execute(
            select(LinkedInConnection).where(LinkedInConnection.member_sub == member_sub)
        )
        connection_by_member = connection_result.scalar_one_or_none()
        if connection_by_member is not None and int(connection_by_member.user_id) != int(user.id):
            logger.warning("LinkedIn member identity is already linked to another application user")
            raise HTTPException(
                status_code=409,
                detail="This LinkedIn account is already connected to another Suvacya account.",
            )

        user.display_name = display_name
        user.is_active = True
        user.is_whitelisted = True

        profile = await session.get(UserProfile, int(user.id))
        if profile is None:
            profile = UserProfile(id=int(user.id), display_name=display_name, role=user.role or "user")
            session.add(profile)
        else:
            profile.display_name = display_name

        if headline and not profile.professional_title:
            profile.professional_title = headline[:200]
        if not profile.tone:
            profile.tone = "Clear, practical and credible"

        connection = connection_by_member
        if connection is None:
            by_user_result = await session.execute(
                select(LinkedInConnection).where(LinkedInConnection.user_id == user.id)
            )
            connection = by_user_result.scalar_one_or_none()

        encrypted_token = encrypt_linkedin_token(access_token)
        if connection is None:
            connection = LinkedInConnection(
                user_id=user.id,
                member_sub=member_sub,
                access_token=encrypted_token,
                token_expires_at=token_expires_at,
                linkedin_email=email,
                linkedin_name=display_name,
                linkedin_headline=headline,
                linkedin_picture_url=picture_url,
                linkedin_locale=locale,
                linkedin_vanity_name=vanity_name,
                linkedin_profile_synced_at=_utc_now(),
            )
            session.add(connection)
        else:
            connection.member_sub = member_sub
            connection.access_token = encrypted_token
            connection.token_expires_at = token_expires_at
            connection.linkedin_email = email
            connection.linkedin_name = display_name

            metadata_added = False
            for attr, value in (
                ("linkedin_headline", headline),
                ("linkedin_picture_url", picture_url),
                ("linkedin_locale", locale),
                ("linkedin_vanity_name", vanity_name),
            ):
                if value and not getattr(connection, attr):
                    setattr(connection, attr, value)
                    metadata_added = True
            if metadata_added:
                connection.linkedin_profile_synced_at = _utc_now()

        exchange_code = secrets.token_urlsafe(32)
        session.add(
            LinkedInOAuthExchange(
                code_hash=_hash(exchange_code),
                user_id=user.id,
                expires_at=_utc_now() + timedelta(minutes=5),
                used=False,
                browser_nonce_hash=browser_nonce_hash,
            )
        )

        # Consume the OAuth state only after every durable write is ready.
        await session.delete(state_row)
        await session.commit()
        return exchange_code

    except HTTPException:
        await session.rollback()
        raise
    except IntegrityError as exc:
        await session.rollback()
        logger.exception("LinkedIn OAuth persistence failed due to database integrity error")
        raise HTTPException(
            status_code=409,
            detail="LinkedIn connection could not be saved because it conflicts with an existing connection.",
        ) from exc
    except Exception as exc:
        await session.rollback()
        logger.exception("LinkedIn OAuth callback failed type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=500,
            detail="LinkedIn sign-in could not be completed. Please try again.",
        ) from exc


async def exchange_code(session: AsyncSession, code: str, browser_nonce: str) -> dict:
    result = await session.execute(
        select(LinkedInOAuthExchange).where(
            LinkedInOAuthExchange.code_hash == _hash(code),
            LinkedInOAuthExchange.expires_at > _utc_now(),
            LinkedInOAuthExchange.used.is_(False),
        )
    )
    exchange = result.scalar_one_or_none()
    if exchange is None:
        raise HTTPException(status_code=400, detail="Invalid or expired LinkedIn exchange code.")

    if not browser_nonce or not hmac.compare_digest(exchange.browser_nonce_hash, _hash(browser_nonce)):
        raise HTTPException(status_code=400, detail="LinkedIn browser verification failed.")

    exchange.used = True
    await session.commit()

    user_result = await session.execute(select(AuthUser).where(AuthUser.id == exchange.user_id))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active or not user.is_whitelisted:
        raise HTTPException(status_code=403, detail="Suvacya user is no longer active or whitelisted.")

    token = await AuthService.create_session(
        session,
        AppUser(
            id=str(user.id),
            email=user.email,
            role=user.role,
            display_name=user.display_name,
            linkedin_url=user.linkedin_url,
        ),
    )
    return {"token": token, "display_name": user.display_name, "role": user.role, "email": user.email}
