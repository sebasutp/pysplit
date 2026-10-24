"""Authentication HTTP endpoints.

Cookies are set here because they are an HTTP concern. All token persistence,
rotation and OAuth account linking live in ``app.services.auth`` and
``app.core.oauth``.
"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.deps import OptionalUser, SessionDep, SettingsDep
from app.core import oauth
from app.core.config import Settings
from app.core.limits import enforce_rate_limit
from app.core.security import (
    constant_time_compare,
    generate_oauth_state,
)
from app.core.validation import safe_return_to
from app.schemas.auth import (
    AuthProviders,
    MeResponse,
    MockLoginRequest,
    MockLoginResponse,
    RefreshResponse,
)
from app.services import auth as auth_service
from app.services.auth import IssuedSession
from app.services.errors import InvalidRefreshTokenError

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Origin, cookie and redirect helpers
# ---------------------------------------------------------------------------


def _normalise_origin(value: str) -> str | None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def request_origin(request: Request, settings: Settings) -> str:
    """Return the canonical public origin for redirects and cookies."""
    if settings.base_url:
        return settings.base_url
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    scheme = forwarded_proto or request.url.scheme
    host = (
        request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    )
    return f"{scheme}://{host}".rstrip("/")


def _require_same_origin(request: Request, settings: Settings) -> None:
    """Reject cookie-authenticated mutations from another site."""
    candidate = request.headers.get("origin")
    if not candidate:
        referer = request.headers.get("referer")
        candidate = _normalise_origin(referer) if referer else None
    normalised = _normalise_origin(candidate) if candidate else None

    allowed = {_normalise_origin(request_origin(request, settings))}
    allowed.update(_normalise_origin(origin) for origin in settings.cors_origins_list)
    allowed.discard(None)
    if normalised is None or normalised not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request origin is not allowed.",
        )


def _require_csrf(request: Request, settings: Settings) -> None:
    cookie = request.cookies.get(settings.csrf_cookie_name)
    header = request.headers.get("x-csrf-token")
    if not constant_time_compare(cookie, header):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing or invalid CSRF token.",
        )


def _set_session_cookies(
    response: Response,
    issued: IssuedSession,
    settings: Settings,
) -> None:
    max_age = settings.refresh_token_ttl_days * 24 * 60 * 60
    response.set_cookie(
        settings.refresh_cookie_name,
        issued.refresh_token,
        max_age=max_age,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path=settings.auth_cookie_path,
    )
    # Readable by the SPA so it can echo the value in X-CSRF-Token.
    response.set_cookie(
        settings.csrf_cookie_name,
        issued.csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )


def _clear_session_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.refresh_cookie_name,
        path=settings.auth_cookie_path,
        secure=settings.secure_cookies,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        settings.csrf_cookie_name,
        path="/",
        secure=settings.secure_cookies,
        httponly=False,
        samesite="lax",
    )


def _set_oauth_state_cookies(
    response: Response,
    *,
    state: str,
    return_to: str,
    settings: Settings,
) -> None:
    max_age = settings.oauth_state_ttl_seconds
    response.set_cookie(
        settings.oauth_state_cookie_name,
        state,
        max_age=max_age,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path=settings.auth_cookie_path,
    )
    response.set_cookie(
        settings.oauth_return_to_cookie_name,
        return_to,
        max_age=max_age,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path=settings.auth_cookie_path,
    )


def _clear_oauth_state_cookies(response: Response, settings: Settings) -> None:
    for name in (
        settings.oauth_state_cookie_name,
        settings.oauth_return_to_cookie_name,
    ):
        response.delete_cookie(
            name,
            path=settings.auth_cookie_path,
            secure=settings.secure_cookies,
            httponly=True,
            samesite="lax",
        )


def _oauth_error_redirect(error: str, settings: Settings) -> RedirectResponse:
    response = RedirectResponse(
        f"/groups?error={error}",
        status_code=status.HTTP_302_FOUND,
    )
    _clear_oauth_state_cookies(response, settings)
    return response


def _refresh_error(
    detail: str,
    settings: Settings,
) -> JSONResponse:
    response = JSONResponse(
        {"detail": detail},
        status_code=status.HTTP_401_UNAUTHORIZED,
        headers={"WWW-Authenticate": "Bearer"},
    )
    _clear_session_cookies(response, settings)
    return response


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/me", response_model=MeResponse)
def me(user: OptionalUser, settings: SettingsDep) -> MeResponse:
    """Return the current user and which OAuth providers are available."""
    enabled = set(settings.enabled_oauth_providers)
    providers = AuthProviders(
        google="google" in enabled,
        github="github" in enabled,
    )
    if user is None:
        return MeResponse(user=None, providers=providers)
    return MeResponse(user=auth_service.user_to_read(user), providers=providers)


@router.get("/oauth/{provider}/start")
def oauth_start(
    provider: str,
    request: Request,
    settings: SettingsDep,
    return_to: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    """Redirect to the provider, storing state and return path in cookies."""
    enforce_rate_limit(request, settings, scope=f"oauth_start:{provider}")

    if not oauth.provider_enabled(provider, settings):
        return _oauth_error_redirect("OAuthNotConfigured", settings)

    origin = request_origin(request, settings)
    redirect_uri = f"{origin}{settings.api_prefix}/auth/oauth/{provider}/callback"
    state = generate_oauth_state()
    authorization_url = oauth.get_authorization_url(
        provider,
        state=state,
        redirect_uri=redirect_uri,
        settings=settings,
    )
    if authorization_url is None:
        return _oauth_error_redirect("OAuthNotConfigured", settings)

    response = RedirectResponse(
        authorization_url,
        status_code=status.HTTP_302_FOUND,
    )
    _set_oauth_state_cookies(
        response,
        state=state,
        return_to=safe_return_to(return_to),
        settings=settings,
    )
    return response


@router.get("/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    """Validate state, exchange the code and start a refresh-token family."""
    enforce_rate_limit(request, settings, scope=f"oauth_callback:{provider}")

    stored_state = request.cookies.get(settings.oauth_state_cookie_name)
    if not code or not state or not constant_time_compare(state, stored_state):
        return _oauth_error_redirect("InvalidOAuthState", settings)

    if not oauth.provider_enabled(provider, settings):
        return _oauth_error_redirect("OAuthNotConfigured", settings)

    return_to = safe_return_to(request.cookies.get(settings.oauth_return_to_cookie_name))
    origin = request_origin(request, settings)
    redirect_uri = f"{origin}{settings.api_prefix}/auth/oauth/{provider}/callback"
    profile = await oauth.exchange_oauth_code(
        provider,
        code=code,
        redirect_uri=redirect_uri,
        settings=settings,
    )
    if profile is None or profile.provider != provider:
        return _oauth_error_redirect("OAuthExchangeFailed", settings)

    user = auth_service.upsert_oauth_user(session, profile)
    enforce_rate_limit(
        request,
        settings,
        scope="oauth_callback_session",
        account_key=user.id,
    )
    issued = auth_service.issue_session(
        session,
        user,
        settings=settings,
        user_agent=request.headers.get("user-agent"),
    )

    response = RedirectResponse(return_to, status_code=status.HTTP_302_FOUND)
    _set_session_cookies(response, issued, settings)
    _clear_oauth_state_cookies(response, settings)
    return response


@router.post("/refresh", response_model=RefreshResponse)
def refresh(
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> RefreshResponse | JSONResponse:
    """Rotate the refresh token and return a new short-lived access token."""
    enforce_rate_limit(request, settings, scope="refresh")
    _require_same_origin(request, settings)
    _require_csrf(request, settings)

    raw_token = request.cookies.get(settings.refresh_cookie_name, "")
    account_id = auth_service.refresh_token_user_id(session, raw_token)
    if account_id:
        enforce_rate_limit(
            request,
            settings,
            scope="refresh_session",
            account_key=account_id,
        )

    try:
        issued = auth_service.rotate_refresh_token(
            session,
            raw_token,
            settings=settings,
            user_agent=request.headers.get("user-agent"),
        )
    except InvalidRefreshTokenError:
        return _refresh_error("Invalid or expired refresh token.", settings)

    _set_session_cookies(response, issued, settings)
    return RefreshResponse(
        access_token=issued.access_token,
        expires_in=issued.expires_in,
        user=auth_service.user_to_read(issued.user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> Response:
    """Revoke the presented refresh token and clear session cookies."""
    enforce_rate_limit(request, settings, scope="logout")
    _require_same_origin(request, settings)
    _require_csrf(request, settings)

    raw_token = request.cookies.get(settings.refresh_cookie_name, "")
    account_id = auth_service.refresh_token_user_id(session, raw_token)
    if account_id:
        enforce_rate_limit(
            request,
            settings,
            scope="logout_session",
            account_key=account_id,
        )

    auth_service.revoke_refresh_token(session, raw_token)
    _clear_session_cookies(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/mock-login", response_model=MockLoginResponse)
def mock_login(
    payload: MockLoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> MockLoginResponse:
    """Development/test login helper. Never available in production."""
    if settings.is_production:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    enforce_rate_limit(request, settings, scope="mock_login")
    _require_same_origin(request, settings)

    user = auth_service.mock_login(
        session,
        email=payload.email,
        name=payload.name,
        tier=payload.tier,
    )
    issued = auth_service.issue_session(
        session,
        user,
        settings=settings,
        user_agent=request.headers.get("user-agent"),
    )
    _set_session_cookies(response, issued, settings)
    return MockLoginResponse(user=auth_service.user_to_read(user))
