import asyncio
import hashlib
import json
import secrets
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import AuthUser, LinkedInConnection, LinkedInOAuthExchange, LinkedInOAuthState, UserProfile
from app.services.auth_service import AppUser, AuthService


LINKEDIN_AUTHORIZE_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def redirect_uri() -> str:
    if settings.linkedin_redirect_uri:
        return settings.linkedin_redirect_uri.rstrip("/")
    base = (settings.api_base_url or settings.render_external_url or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=500, detail="API_BASE_URL is not configured")
    return f"{base}/api/auth/linkedin/callback"


def _request_json(url: str, *, data: dict | None = None, headers: dict | None = None) -> dict:
    encoded = urllib.parse.urlencode(data).encode("utf-8") if data is not None else None
    request = urllib.request.Request(
        url,
        data=encoded,
        headers=headers or {},
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LinkedIn API request failed: {exc}") from exc


def _best_effort_profile(access_token: str, userinfo: dict) -> dict:
    """Return profile fields LinkedIn makes available to this OAuth app.

    OIDC always gives us identity fields. Some LinkedIn products also expose
    headline/public-profile details through the same member token. The extra
    call is deliberately best-effort so a restricted LinkedIn app never blocks
    authentication.
    """
    profile = dict(userinfo or {})
    try:
        member = _request_json(
            "https://api.linkedin.com/v2/me",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Linkedin-Version": settings.linkedin_api_version,
                "X-Restli-Protocol-Version": "2.0.0",
            },
        )
        if isinstance(member, dict):
            for key, value in member.items():
                if key not in profile or not profile.get(key):
                    profile[key] = value
    except HTTPException:
        # The OIDC token may not have the legacy Profile API permission.
        # Authentication and the basic LinkedIn identity must still work.
        pass
    return profile


def _localized_value(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        localized = value.get("localized")
        if isinstance(localized, dict):
            for item in localized.values():
                if isinstance(item, str) and item.strip():
                    return item.strip()
    return None


async def build_authorization_url(session: AsyncSession) -> str:
    if not settings.linkedin_client_id or not settings.linkedin_client_secret:
        raise HTTPException(
            status_code=503,
            detail="LinkedIn OAuth is not configured. Add LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET in Render.",
        )

    state = secrets.token_urlsafe(32)
    session.add(
        LinkedInOAuthState(
            state_hash=_hash(state),
            expires_at=_utc_now() + timedelta(minutes=10),
        )
    )
    await session.commit()

    scopes = ["openid", "profile", "email", "w_member_social"]
    if settings.linkedin_analytics_oauth_enabled:
        scopes.extend(["r_member_postAnalytics", "r_member_profileAnalytics"])

    params = {
        "response_type": "code",
        "client_id": settings.linkedin_client_id,
        "redirect_uri": redirect_uri(),
        "state": state,
        "scope": " ".join(scopes),
    }
    return f"{LINKEDIN_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


async def handle_callback(session: AsyncSession, code: str, state: str) -> str:
    result = await session.execute(
        select(LinkedInOAuthState).where(
            LinkedInOAuthState.state_hash == _hash(state),
            LinkedInOAuthState.expires_at > _utc_now(),
        )
    )
    state_row = result.scalar_one_or_none()
    if state_row is None:
        raise HTTPException(status_code=400, detail="Invalid or expired LinkedIn OAuth state.")

    await session.delete(state_row)
    await session.commit()

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

    access_token = token_payload.get("access_token")
    if not access_token:
        raise HTTPException(status_code=502, detail="LinkedIn did not return an access token.")

    expires_in = token_payload.get("expires_in")
    token_expires_at = _utc_now() + timedelta(seconds=int(expires_in)) if expires_in else None

    userinfo = await asyncio.to_thread(
        _request_json,
        LINKEDIN_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    profile_data = await asyncio.to_thread(_best_effort_profile, access_token, userinfo)

    email = AuthService.normalize_email(profile_data.get("email"))
    member_sub = profile_data.get("sub") or profile_data.get("id")
    display_name = profile_data.get("name") or "LinkedIn Member"
    professional_title = (
        profile_data.get("headline")
        or profile_data.get("localizedHeadline")
        or _localized_value(profile_data.get("headline"))
    )
    industry = (
        profile_data.get("industryName")
        or profile_data.get("localizedIndustry")
        or _localized_value(profile_data.get("industry"))
    )
    vanity_name = profile_data.get("vanityName")
    profile_url = (
        "https://www.linkedin.com/in/" + str(vanity_name).strip()
        if vanity_name and str(vanity_name).strip()
        else None
    )

    if not email or not member_sub:
        raise HTTPException(status_code=403, detail="LinkedIn did not return the required member identity.")

    # The Supabase/Postgres auth_users table is the single source of truth.
    # Adding an email there is sufficient to authorize a new user.
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

    user.display_name = display_name
    user.is_active = True
    user.is_whitelisted = True

    # Keep the authenticated LinkedIn profile as the factual Brand DNA baseline.
    # User-controlled Brand DNA fields are only filled when LinkedIn actually
    # supplies them; we never invent profile facts during sign-in.
    if profile_url:
        user.linkedin_url = profile_url

    profile = await session.get(UserProfile, 1)
    if profile is None:
        profile = UserProfile(id=1, display_name=display_name, role="owner")
        session.add(profile)
    else:
        profile.display_name = display_name

    if professional_title:
        profile.professional_title = str(professional_title)[:200]
    if industry:
        profile.industry = str(industry)[:200]

    connection_result = await session.execute(
        select(LinkedInConnection).where(LinkedInConnection.user_id == user.id)
    )
    connection = connection_result.scalar_one_or_none()
    if connection is None:
        connection = LinkedInConnection(
            user_id=user.id,
            member_sub=member_sub,
            access_token=access_token,
            token_expires_at=token_expires_at,
            linkedin_email=email,
            linkedin_name=display_name,
        )
        session.add(connection)
    else:
        connection.member_sub = member_sub
        connection.access_token = access_token
        connection.token_expires_at = token_expires_at
        connection.linkedin_email = email
        connection.linkedin_name = display_name

    exchange_code = secrets.token_urlsafe(32)
    session.add(
        LinkedInOAuthExchange(
            code_hash=_hash(exchange_code),
            user_id=user.id,
            expires_at=_utc_now() + timedelta(minutes=5),
            used=False,
        )
    )
    await session.commit()
    return exchange_code


async def sync_linkedin_profile(session: AsyncSession, user_id: int) -> dict:
    """Refresh the connected member's LinkedIn-backed Brand DNA profile."""
    connection_result = await session.execute(
        select(LinkedInConnection).where(LinkedInConnection.user_id == user_id)
    )
    connection = connection_result.scalar_one_or_none()
    if connection is None:
        raise HTTPException(status_code=404, detail="LinkedIn account is not connected.")

    user = await session.get(AuthUser, user_id)
    if user is None or not user.is_active or not user.is_whitelisted:
        raise HTTPException(status_code=403, detail="Brand OS user is no longer active or whitelisted.")

    userinfo = await asyncio.to_thread(
        _request_json,
        LINKEDIN_USERINFO_URL,
        headers={"Authorization": f"Bearer {connection.access_token}"},
    )
    profile_data = await asyncio.to_thread(_best_effort_profile, connection.access_token, userinfo)

    display_name = profile_data.get("name") or user.display_name or "LinkedIn Member"
    professional_title = (
        profile_data.get("headline")
        or profile_data.get("localizedHeadline")
        or _localized_value(profile_data.get("headline"))
    )
    industry = (
        profile_data.get("industryName")
        or profile_data.get("localizedIndustry")
        or _localized_value(profile_data.get("industry"))
    )
    vanity_name = profile_data.get("vanityName")
    profile_url = (
        "https://www.linkedin.com/in/" + str(vanity_name).strip()
        if vanity_name and str(vanity_name).strip()
        else user.linkedin_url
    )

    user.display_name = str(display_name)[:150]
    if profile_url:
        user.linkedin_url = str(profile_url)[:255]

    profile = await session.get(UserProfile, 1)
    if profile is None:
        profile = UserProfile(id=1, display_name=str(display_name)[:150], role="owner")
        session.add(profile)
    else:
        profile.display_name = str(display_name)[:150]

    if professional_title:
        profile.professional_title = str(professional_title)[:200]
    if industry:
        profile.industry = str(industry)[:200]

    await session.commit()
    return {
        "display_name": profile.display_name,
        "professional_title": profile.professional_title,
        "industry": profile.industry,
        "linkedin_url": user.linkedin_url,
        "source": "linkedin",
    }


async def exchange_code(session: AsyncSession, code: str) -> dict:
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

    exchange.used = True
    await session.commit()

    user_result = await session.execute(select(AuthUser).where(AuthUser.id == exchange.user_id))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active or not user.is_whitelisted:
        raise HTTPException(status_code=403, detail="Brand OS user is no longer active or whitelisted.")

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
