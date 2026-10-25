"""Authentication HTTP endpoints.

Cookies are set here because they are an HTTP concern. All token persistence,
rotation and OAuth account linking live in ``app.services.auth`` and
``app.core.oauth``.
"""

from __future__ import annotations

import re
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
    """Return the canonical public origin for redirects and cookies.

    Forwarded headers are only honoured when the deployment explicitly opts
    in; otherwise a client could spoof the origin used for CSRF checks and
    OAuth redirect URIs.
    """
    if settings.base_url:
        return settings.base_url
    scheme = request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    if settings.trust_forwarded_headers:
        forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
        scheme = forwarded_proto or scheme
        host = request.headers.get("x-forwarded-host") or host
    return f"{scheme}://{host}".rstrip("/")


def request_is_https(request: Request, settings: Settings) -> bool:
    """Whether the browser reached the app over HTTPS.

    ``BASE_URL`` wins when configured. Otherwise a trusted reverse proxy's
    ``X-Forwarded-Proto`` is the only reliable signal.
    """
    if settings.base_url:
        return settings.base_url.lower().startswith("https://")
    if settings.trust_forwarded_headers:
        forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
        if forwarded_proto:
            return forwarded_proto.lower() == "https"
    return request.url.scheme == "https"


def secure_cookies_for_request(request: Request, settings: Settings) -> bool:
    # An explicit COOKIE_SECURE setting wins over the request scheme.
    if settings.cookie_secure is not None:
        return settings.cookie_secure
    return settings.secure_cookies or request_is_https(request, settings)


def app_redirect_target(path: str, settings: Settings) -> str:
    """Prefix an app-relative path with the configured SPA origin.

    When the SPA is served from the same origin as the API (for example behind
    a reverse proxy that forwards ``/api``), the relative path is kept. With a
    split frontend/backend the browser must land back on the SPA instead of on
    the API host.
    """
    if settings.frontend_url:
        return f"{settings.frontend_url}{path}"
    return path


def _origin_is_allowed(origin: str | None, settings: Settings) -> bool:
    if origin is None:
        return False
    normalised = _normalise_origin(origin)
    if normalised is None:
        return False
    if normalised in settings.allowed_origins_list:
        return True
    if settings.cors_origin_regex:
        return re.fullmatch(settings.cors_origin_regex, normalised) is not None
    return False


def _require_same_origin(request: Request, settings: Settings) -> None:
    """Reject cookie-authenticated mutations from another site."""
    candidate = request.headers.get("origin")
    if not candidate:
        referer = request.headers.get("referer")
        candidate = _normalise_origin(referer) if referer else None
    normalised = _normalise_origin(candidate) if candidate else None

    allowed = {_normalise_origin(request_origin(request, settings))}
    allowed.update(settings.allowed_origins_list)
    allowed.discard(None)
    if not _origin_is_allowed(normalised, settings) and normalised not in allowed:
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
    *,
    secure: bool,
) -> None:
    max_age = settings.refresh_token_ttl_days * 24 * 60 * 60
    response.set_cookie(
        settings.refresh_cookie_name,
        issued.refresh_token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite=settings.cookie_samesite,
        path=settings.auth_cookie_path,
    )
    # Readable by the SPA so it can echo the value in X-CSRF-Token. A
    # cross-origin SPA cannot read this host-only cookie, so it is optionally
    # shared with sibling subdomains (COOKIE_DOMAIN) and the same token is
    # also returned by /me, /refresh and /mock-login. The refresh cookie stays
    # host-only.
    response.set_cookie(
        settings.csrf_cookie_name,
        issued.csrf_token,
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite=settings.cookie_samesite,
        path="/",
        domain=settings.cookie_domain,
    )


def _clear_session_cookies(response: Response, settings: Settings, *, secure: bool) -> None:
    response.delete_cookie(
        settings.refresh_cookie_name,
        path=settings.auth_cookie_path,
        secure=secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )
    response.delete_cookie(
        settings.csrf_cookie_name,
        path="/",
        secure=secure,
        httponly=False,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
    )


def _set_oauth_state_cookies(
    response: Response,
    *,
    state: str,
    return_to: str,
    settings: Settings,
    secure: bool,
) -> None:
    max_age = settings.oauth_state_ttl_seconds
    response.set_cookie(
        settings.oauth_state_cookie_name,
        state,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite=settings.cookie_samesite,
        path=settings.auth_cookie_path,
    )
    response.set_cookie(
        settings.oauth_return_to_cookie_name,
        return_to,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite=settings.cookie_samesite,
        path=settings.auth_cookie_path,
    )


def _clear_oauth_state_cookies(
    response: Response,
    settings: Settings,
    *,
    secure: bool,
) -> None:
    for name in (
        settings.oauth_state_cookie_name,
        settings.oauth_return_to_cookie_name,
    ):
        response.delete_cookie(
            name,
            path=settings.auth_cookie_path,
            secure=secure,
            httponly=True,
            samesite=settings.cookie_samesite,
        )


def _oauth_error_redirect(error: str, settings: Settings, *, secure: bool) -> RedirectResponse:
    response = RedirectResponse(
        app_redirect_target(f"/groups?error={error}", settings),
        status_code=status.HTTP_302_FOUND,
    )
    _clear_oauth_state_cookies(response, settings, secure=secure)
    return response


def _refresh_error(
    detail: str,
    settings: Settings,
    *,
    secure: bool,
) -> JSONResponse:
    response = JSONResponse(
        {"detail": detail},
        status_code=status.HTTP_401_UNAUTHORIZED,
        headers={"WWW-Authenticate": "Bearer"},
    )
    _clear_session_cookies(response, settings, secure=secure)
    return response


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/me", response_model=MeResponse)
def me(user: OptionalUser, request: Request, settings: SettingsDep) -> MeResponse:
    """Return the current user and which OAuth providers are available."""
    enabled = set(settings.enabled_oauth_providers)
    providers = AuthProviders(
        google="google" in enabled,
        github="github" in enabled,
    )
    csrf_token = request.cookies.get(settings.csrf_cookie_name) or None
    if user is None:
        return MeResponse(user=None, providers=providers, csrf_token=csrf_token)
    return MeResponse(
        user=auth_service.user_to_read(user),
        providers=providers,
        csrf_token=csrf_token,
    )


@router.get("/oauth/{provider}/start")
def oauth_start(
    provider: str,
    request: Request,
    settings: SettingsDep,
    return_to: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    """Redirect to the provider, storing state and return path in cookies."""
    enforce_rate_limit(request, settings, scope=f"oauth_start:{provider}")
    secure = secure_cookies_for_request(request, settings)

    if not oauth.provider_enabled(provider, settings):
        return _oauth_error_redirect("OAuthNotConfigured", settings, secure=secure)

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
        return _oauth_error_redirect("OAuthNotConfigured", settings, secure=secure)

    response = RedirectResponse(
        authorization_url,
        status_code=status.HTTP_302_FOUND,
    )
    _set_oauth_state_cookies(
        response,
        state=state,
        return_to=safe_return_to(
            return_to,
            allowed_origins=(request_origin(request, settings), settings.frontend_url or ""),
        ),
        settings=settings,
        secure=secure,
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
    secure = secure_cookies_for_request(request, settings)

    stored_state = request.cookies.get(settings.oauth_state_cookie_name)
    if not code or not state or not constant_time_compare(state, stored_state):
        return _oauth_error_redirect("InvalidOAuthState", settings, secure=secure)

    if not oauth.provider_enabled(provider, settings):
        return _oauth_error_redirect("OAuthNotConfigured", settings, secure=secure)

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
        return _oauth_error_redirect("OAuthExchangeFailed", settings, secure=secure)

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

    response = RedirectResponse(
        app_redirect_target(return_to, settings),
        status_code=status.HTTP_302_FOUND,
    )
    _set_session_cookies(response, issued, settings, secure=secure)
    _clear_oauth_state_cookies(response, settings, secure=secure)
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
    secure = secure_cookies_for_request(request, settings)
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
        return _refresh_error("Invalid or expired refresh token.", settings, secure=secure)

    _set_session_cookies(response, issued, settings, secure=secure)
    return RefreshResponse(
        access_token=issued.access_token,
        expires_in=issued.expires_in,
        user=auth_service.user_to_read(issued.user),
        csrf_token=issued.csrf_token,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> Response:
    """Revoke the refresh-token family and clear session cookies."""
    enforce_rate_limit(request, settings, scope="logout")
    secure = secure_cookies_for_request(request, settings)
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

    auth_service.revoke_refresh_family(session, raw_token)
    _clear_session_cookies(response, settings, secure=secure)
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
    """Development/test login helper. Opt-in and never available in production."""
    if not settings.enable_mock_login or settings.is_production:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    enforce_rate_limit(request, settings, scope="mock_login")
    secure = secure_cookies_for_request(request, settings)
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
    _set_session_cookies(response, issued, settings, secure=secure)
    return MockLoginResponse(
        user=auth_service.user_to_read(user),
        csrf_token=issued.csrf_token,
    )
