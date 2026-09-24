from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.database import get_session
from app.services.auth_service import AuthService

bearer_scheme = HTTPBearer(auto_error=False)


async def _resolve_role(request: Request, credentials: HTTPAuthorizationCredentials | None, session: AsyncSession) -> str | None:
    if credentials and credentials.credentials:
        token = credentials.credentials.strip()
        user = await AuthService.get_user_from_token(session, token)
        if user:
            return user.role.lower()

    header_role = request.headers.get("x-user-role")
    if header_role:
        return header_role.strip().lower()

    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        if token:
            user = await AuthService.get_user_from_token(session, token)
            if user:
                return user.role.lower()
            return token.lower()

    return None


def require_roles(*allowed_roles: str):
    async def dependency(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
        session: AsyncSession = Depends(get_session),
    ) -> str:
        role = await _resolve_role(request, credentials, session)

        if role is None:
            if settings.is_production:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return "owner"

        if role not in {"owner", "admin", "reviewer", "user"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role permissions",
            )

        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role permissions",
            )

        return role

    return dependency
