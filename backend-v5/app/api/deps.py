"""API dependencies for dependency injection."""
from typing import AsyncGenerator, Callable, List
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.user import User, UserRole
from app.services.auth_service import AuthService

# HTTP Bearer token scheme
security = HTTPBearer(auto_error=False)

PUBLIC_READ_ROUTE_PREFIXES = (
    "/api/v1/dashboard/bootstrap",
    "/api/v1/kpi/snapshot",
    "/api/v1/kpi/trends/hourly",
    "/api/v1/stories/recent",
    "/api/v1/stories/sources",
    "/api/v1/stories",
    "/api/v1/map/events",
    "/api/v1/announcements/summary",
    "/api/v1/twitter/tweets",
    "/api/v1/verbatim/summary",
    "/api/v1/verbatim/scoreboard",
    "/api/v1/verbatim/sessions",
    "/api/v1/briefs/latest",
    "/api/v1/briefs/history",
    "/api/v1/province-anomalies/latest",
    "/api/v1/parliament/bills",
    "/api/v1/parliament/questions/as-sessions",
    "/api/v1/disaster-alerts/active",
    "/api/v1/disaster-alerts/stats",
    "/api/v1/disaster-alerts/map-data",
    "/api/v1/fact-check/results",
    "/api/v1/analytics/story-tracker",
    "/api/v1/analytics/developing-stories",
    "/api/v1/analytics/consolidated-stories",
    "/api/v1/weather/summary",
    "/api/v1/market/summary",
    "/api/v1/debt-clock/nepal",
    "/api/v1/infrastructure/border-crossings",
    "/api/v1/govt-decisions/latest",
    "/api/v1/procurement/widget-summary",
    "/api/v1/economy/nrb-snapshot",
    "/api/v1/cabinet-actions/summary",
    "/api/v1/cabinet-actions/items",
    "/api/v1/election-results/house-representatives",
    "/api/v1/promises",
    "/api/v1/promises/summary",
)


def _is_public_read_route(request: Request) -> bool:
    if request.method.upper() not in {"GET", "HEAD"}:
        return False

    path = request.url.path
    return any(
        path == prefix or path.startswith(prefix + "/")
        for prefix in PUBLIC_READ_ROUTE_PREFIXES
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session dependency."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_current_user(
    request: Request,
    token: str | None = Query(default=None),
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """Get the current authenticated user from the JWT token.

    Uses a short-lived DB session that closes immediately after the user
    lookup — does NOT hold a connection for the entire request duration.
    This halves connection pressure vs the old approach where auth held
    its own get_db session open alongside the endpoint's session.
    """
    is_public_read = _is_public_read_route(request)

    if credentials:
        raw_token = credentials.credentials
    elif token and request.method.upper() == "GET":
        raw_token = token
    elif is_public_read:
        return AuthService.build_public_consumer_user()
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = AuthService.decode_token(raw_token)

    if not payload:
        if is_public_read:
            return AuthService.build_public_consumer_user()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.type != "access":
        if is_public_read:
            return AuthService.build_public_consumer_user()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.public_consumer or payload.auth_provider == "public":
        return AuthService.build_public_consumer_user()

    # Short-lived session — closes immediately after user fetch.
    # The old code used Depends(get_db) which held the connection open
    # for the entire request lifecycle, doubling pool pressure.
    async with AsyncSessionLocal() as db:
        auth_service = AuthService(db)
        user = await auth_service.get_user_by_id(UUID(payload.sub))

    if not user:
        if is_public_read:
            return AuthService.build_public_consumer_user()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        if is_public_read:
            return AuthService.build_public_consumer_user()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_user_optional(
    request: Request,
    token: str | None = Query(default=None),
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User | None:
    """
    Get the current user if authenticated, otherwise return None.
    Useful for routes that work differently for authenticated vs anonymous users.
    """
    if not credentials and not token:
        return None

    try:
        return await get_current_user(
            request=request,
            token=token,
            credentials=credentials,
        )
    except HTTPException:
        return None


def require_role(allowed_roles: List[UserRole]) -> Callable:
    """
    Create a dependency that requires the user to have one of the specified roles.

    Usage:
        @router.get("/admin")
        async def admin_route(user: User = Depends(require_role([UserRole.DEV]))):
            ...
    """
    async def role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {[r.value for r in allowed_roles]}",
            )
        return user

    return role_checker


# Convenience dependencies for common role combinations
async def require_analyst(
    user: User = Depends(get_current_user),
) -> User:
    """Require analyst or dev role."""
    if not user.is_analyst_or_above():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requires analyst or dev role",
        )
    return user


async def require_persistent_user(
    user: User = Depends(get_current_user),
) -> User:
    """Require a user that actually exists as a row in `users`.

    /auth/public hands anonymous visitors a synthetic identity whose id is a
    derived UUID5 with no matching row, so any endpoint that persists per-user
    state (notification preferences, read marks, follows) would otherwise fail
    with a ForeignKeyViolationError surfacing as a 500. Reject it up front with
    a 403 the client can reason about; reads stay open to anonymous visitors.
    """
    if AuthService.is_public_consumer(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sign in to save preferences",
        )
    return user


async def require_dev(
    user: User = Depends(get_current_user),
) -> User:
    """Require dev role."""
    if not user.is_dev():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requires dev role",
        )
    return user
