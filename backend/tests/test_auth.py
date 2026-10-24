"""Stage 4 authentication tests.

Covers token tampering/expiry, refresh rotation and reuse, CSRF and origin
checks, OAuth state, open-redirect rejection, email linking and provider
discovery. No real OAuth network calls are made.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from app.core import oauth
from app.core.config import Settings
from app.core.enums import UserTier
from app.core.oauth import OAuthProfile
from app.core.security import (
    TokenError,
    create_access_token,
    hash_refresh_token,
    verify_access_token,
)
from app.models.account import Account
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services import auth as auth_service
from app.services.errors import InvalidRefreshTokenError, RefreshTokenReuseError
from tests.helpers import access_headers, csrf_headers, make_user, mock_login


def _login(client: TestClient, email: str = "alice@example.com", **kwargs) -> User:
    response = mock_login(client, email=email, **kwargs)
    assert response.status_code == 200, response.text
    return response.json()["user"]


# ---------------------------------------------------------------------------
# Access tokens and /me
# ---------------------------------------------------------------------------


def test_me_anonymous(client: TestClient) -> None:
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["user"] is None
    assert response.json()["providers"] == {"google": False, "github": False}


def test_me(client: TestClient, session) -> None:
    user = make_user(session, email="ada@example.com", name="Ada", tier=UserTier.ADMIN)
    response = client.get("/api/auth/me", headers=access_headers(user))
    assert response.status_code == 200
    assert response.json()["user"] == {
        "id": user.id,
        "name": "Ada",
        "email": "ada@example.com",
        "image": None,
        "tier": "admin",
    }


def test_session(client: TestClient, session) -> None:
    """The reference ``session`` endpoint is served by ``/api/auth/me``."""
    user = make_user(session, email="session@example.com")
    response = client.get("/api/auth/me", headers=access_headers(user))
    assert response.status_code == 200
    assert response.json()["user"]["id"] == user.id


def test_me_invalid_token_is_anonymous(client: TestClient) -> None:
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.token"})
    assert response.status_code == 200
    assert response.json()["user"] is None


def test_tampered_token_is_rejected() -> None:
    settings = Settings(_env_file=None)
    token = create_access_token("usr_1", secret=settings.jwt_secret, ttl_seconds=900)
    header, payload, signature = token.split(".")
    tampered_payload = payload[:-2] + ("aa" if payload[-2:] != "aa" else "bb")
    with pytest.raises(TokenError):
        verify_access_token(
            f"{header}.{tampered_payload}.{signature}",
            secret=settings.jwt_secret,
        )
    with pytest.raises(TokenError):
        verify_access_token(
            f"{header}.{payload}.{signature[:-2]}xx",
            secret=settings.jwt_secret,
        )


def test_expired_access_token_is_rejected() -> None:
    settings = Settings(_env_file=None)
    past = datetime.now(UTC) - timedelta(hours=1)
    token = create_access_token(
        "usr_1",
        secret=settings.jwt_secret,
        ttl_seconds=300,
        now=past,
    )
    with pytest.raises(TokenError):
        verify_access_token(token, secret=settings.jwt_secret)


def test_expired_access_token_does_not_authenticate(client: TestClient, session) -> None:
    user = make_user(session, email="expired@example.com")
    token = create_access_token(
        user.id,
        secret=Settings(_env_file=None).jwt_secret,
        ttl_seconds=1,
        now=datetime.now(UTC) - timedelta(minutes=5),
    )
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["user"] is None


# ---------------------------------------------------------------------------
# Refresh, rotation and logout
# ---------------------------------------------------------------------------


def test_refresh_rotates_tokens(client: TestClient) -> None:
    _login(client)
    old_refresh = client.cookies.get("pysplit_refresh")
    old_csrf = client.cookies.get("pysplit_csrf")
    assert old_refresh and old_csrf

    response = client.post("/api/auth/refresh", headers=csrf_headers(client))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["expires_in"] == 900
    assert payload["user"]["tier"] == "sync_users"

    new_refresh = client.cookies.get("pysplit_refresh")
    new_csrf = client.cookies.get("pysplit_csrf")
    assert new_refresh and new_csrf
    assert new_refresh != old_refresh
    assert new_csrf != old_csrf

    me = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "alice@example.com"


def test_refresh_reuse_over_http_revokes_family(client: TestClient) -> None:
    _login(client)
    old_refresh = client.cookies.get("pysplit_refresh")
    first = client.post("/api/auth/refresh", headers=csrf_headers(client))
    assert first.status_code == 200
    new_refresh = client.cookies.get("pysplit_refresh")
    new_csrf = client.cookies.get("pysplit_csrf")
    assert old_refresh and new_refresh and new_csrf

    client.cookies.clear()
    reuse = client.post(
        "/api/auth/refresh",
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": new_csrf,
            "Cookie": f"pysplit_refresh={old_refresh}; pysplit_csrf={new_csrf}",
        },
    )
    assert reuse.status_code == 401

    client.cookies.clear()
    revoked = client.post(
        "/api/auth/refresh",
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": new_csrf,
            "Cookie": f"pysplit_refresh={new_refresh}; pysplit_csrf={new_csrf}",
        },
    )
    assert revoked.status_code == 401


def test_refresh_without_csrf_is_rejected(client: TestClient) -> None:
    _login(client)
    response = client.post("/api/auth/refresh", headers={"Origin": "http://testserver"})
    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]


def test_refresh_with_wrong_csrf_is_rejected(client: TestClient) -> None:
    _login(client)
    response = client.post(
        "/api/auth/refresh",
        headers={"Origin": "http://testserver", "X-CSRF-Token": "wrong"},
    )
    assert response.status_code == 403


def test_refresh_from_another_origin_is_rejected(client: TestClient) -> None:
    _login(client)
    headers = csrf_headers(client, origin="https://evil.example")
    response = client.post("/api/auth/refresh", headers=headers)
    assert response.status_code == 403
    assert "origin" in response.json()["detail"].lower()


def test_refresh_without_cookie_is_rejected(client: TestClient) -> None:
    client.cookies.set("pysplit_csrf", "token", path="/")
    response = client.post(
        "/api/auth/refresh",
        headers={"Origin": "http://testserver", "X-CSRF-Token": "token"},
    )
    assert response.status_code == 401


def test_refresh_reuse_detection(session) -> None:
    settings = Settings(_env_file=None)
    user = make_user(session, email="rotate@example.com")
    issued = auth_service.issue_session(session, user, settings=settings)
    rotated = auth_service.rotate_refresh_token(session, issued.refresh_token, settings=settings)
    with pytest.raises(RefreshTokenReuseError):
        auth_service.rotate_refresh_token(session, issued.refresh_token, settings=settings)
    # Reuse revoked the whole family, including the token that replaced it.
    with pytest.raises((RefreshTokenReuseError, InvalidRefreshTokenError)):
        auth_service.rotate_refresh_token(session, rotated.refresh_token, settings=settings)


def test_expired_refresh_token_is_rejected(session) -> None:
    settings = Settings(_env_file=None)
    user = make_user(session, email="refresh-expired@example.com")
    issued = auth_service.issue_session(session, user, settings=settings)
    record = session.exec(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(issued.refresh_token)
        )
    ).first()
    assert record is not None
    record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.add(record)
    session.commit()

    with pytest.raises(InvalidRefreshTokenError):
        auth_service.rotate_refresh_token(session, issued.refresh_token, settings=settings)


def test_logout_revokes_refresh_token(client: TestClient) -> None:
    _login(client)
    raw_refresh = client.cookies.get("pysplit_refresh")
    assert raw_refresh

    response = client.post("/api/auth/logout", headers=csrf_headers(client))
    assert response.status_code == 204
    assert response.content == b""
    assert client.cookies.get("pysplit_refresh") in (None, "")

    # Re-present the revoked token with a valid-looking CSRF pair.
    client.cookies.set("pysplit_refresh", raw_refresh, path="/api/auth")
    client.cookies.set("pysplit_csrf", "csrf", path="/")
    retry = client.post(
        "/api/auth/refresh",
        headers={"Origin": "http://testserver", "X-CSRF-Token": "csrf"},
    )
    assert retry.status_code == 401


def test_refresh_cookie_is_scoped_and_httponly(client: TestClient) -> None:
    response = mock_login(client, email="cookie@example.com")
    cookies = response.headers.get_list("set-cookie")
    refresh_cookie = next(cookie for cookie in cookies if cookie.startswith("pysplit_refresh="))
    assert "HttpOnly" in refresh_cookie
    assert "Path=/api/auth" in refresh_cookie
    assert "SameSite=lax" in refresh_cookie


# ---------------------------------------------------------------------------
# OAuth start, callback, state and redirects
# ---------------------------------------------------------------------------


def _google_client(make_client):
    return make_client(
        auth_google_id="google-id",
        auth_google_secret="google-secret",
        base_url="http://testserver",
    )


def test_oauth_start(make_client) -> None:
    client = _google_client(make_client)
    response = client.get(
        "/api/auth/oauth/google/start?return_to=/groups/abc",
        follow_redirects=False,
    )
    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith(oauth.GOOGLE_AUTHORIZE_URL)
    assert (
        "redirect_uri=http%3A%2F%2Ftestserver%2Fapi%2Fauth%2Foauth%2Fgoogle%2Fcallback" in location
    )
    assert "state=" in location
    assert client.cookies.get("pysplit_oauth_state")
    assert client.cookies.get("pysplit_oauth_return_to").strip('"') == "/groups/abc"


def test_oauth_start_unconfigured_provider(client: TestClient) -> None:
    response = client.get("/api/auth/oauth/github/start", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/groups?error=OAuthNotConfigured"


def test_oauth_start_unknown_provider(client: TestClient) -> None:
    response = client.get("/api/auth/oauth/facebook/start", follow_redirects=False)
    assert response.status_code == 302
    assert "OAuthNotConfigured" in response.headers["location"]


def test_provider_discovery() -> None:
    configured = Settings(
        auth_google_id="id",
        auth_google_secret="secret",
        _env_file=None,
    )
    assert configured.enabled_oauth_providers == ["google"]
    assert oauth.provider_enabled("google", configured)
    assert not oauth.provider_enabled("github", configured)
    assert not oauth.provider_enabled("facebook", configured)
    assert (
        oauth.get_authorization_url(
            "github", state="s", redirect_uri="http://x/cb", settings=configured
        )
        is None
    )

    both = Settings(
        auth_google_id="id",
        auth_google_secret="secret",
        auth_github_id="gh",
        auth_github_secret="ghsecret",
        _env_file=None,
    )
    assert both.enabled_oauth_providers == ["google", "github"]


def test_me_reports_enabled_providers(make_client) -> None:
    client = make_client(
        auth_google_id="id",
        auth_google_secret="secret",
        auth_github_id="gh",
        auth_github_secret="ghsecret",
    )
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["providers"] == {"google": True, "github": True}


def test_oauth_open_redirect_is_rejected(make_client) -> None:
    client = _google_client(make_client)
    client.get(
        "/api/auth/oauth/google/start?return_to=https://evil.example/steal",
        follow_redirects=False,
    )
    assert client.cookies.get("pysplit_oauth_return_to").strip('"') == "/groups"

    client.get(
        "/api/auth/oauth/google/start?return_to=//evil.example",
        follow_redirects=False,
    )
    assert client.cookies.get("pysplit_oauth_return_to").strip('"') == "/groups"


def test_oauth_callback_never_redirects_off_site(
    make_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _google_client(make_client)
    client.get(
        "/api/auth/oauth/google/start?return_to=https://evil.example/steal",
        follow_redirects=False,
    )
    state = client.cookies.get("pysplit_oauth_state")
    _stub_exchange(
        monkeypatch,
        OAuthProfile(
            provider="google",
            provider_account_id="google-open-redirect",
            name=None,
            email=None,
            image=None,
        ),
    )
    response = client.get(
        f"/api/auth/oauth/google/callback?code=code&state={state}",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/groups"


def _stub_exchange(monkeypatch: pytest.MonkeyPatch, profile: OAuthProfile | None):
    async def fake(*_args, **_kwargs):
        return profile

    monkeypatch.setattr(oauth, "exchange_oauth_code", fake)


def test_oauth_callback_creates_user_and_session(
    make_client, session, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _google_client(make_client)
    client.get(
        "/api/auth/oauth/google/start?return_to=/groups/trip",
        follow_redirects=False,
    )
    state = client.cookies.get("pysplit_oauth_state")
    _stub_exchange(
        monkeypatch,
        OAuthProfile(
            provider="google",
            provider_account_id="google-123",
            name="Grace Hopper",
            email="Grace@Example.com",
            image="https://example.com/grace.png",
        ),
    )

    response = client.get(
        f"/api/auth/oauth/google/callback?code=code&state={state}",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/groups/trip"
    assert client.cookies.get("pysplit_refresh")
    assert client.cookies.get("pysplit_csrf")

    user = session.exec(select(User)).one()
    assert user.email == "grace@example.com"
    assert user.name == "Grace Hopper"
    assert user.tier == "sync_users"
    account = session.exec(select(Account)).one()
    assert account.provider == "google"
    assert account.provider_account_id == "google-123"

    refresh = client.post("/api/auth/refresh", headers=csrf_headers(client))
    assert refresh.status_code == 200
    assert refresh.json()["user"]["email"] == "grace@example.com"


def test_oauth_callback_state_mismatch(
    make_client, session, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _google_client(make_client)
    client.get("/api/auth/oauth/google/start", follow_redirects=False)
    _stub_exchange(
        monkeypatch,
        OAuthProfile(
            provider="google",
            provider_account_id="google-123",
            name=None,
            email=None,
            image=None,
        ),
    )

    response = client.get(
        "/api/auth/oauth/google/callback?code=code&state=wrong",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/groups?error=InvalidOAuthState"
    assert session.exec(select(User)).first() is None


def test_oauth_callback_requires_stored_state(
    make_client, session, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _google_client(make_client)
    _stub_exchange(
        monkeypatch,
        OAuthProfile(
            provider="google",
            provider_account_id="google-123",
            name=None,
            email=None,
            image=None,
        ),
    )
    response = client.get(
        "/api/auth/oauth/google/callback?code=code&state=anything",
        follow_redirects=False,
    )
    assert response.headers["location"] == "/groups?error=InvalidOAuthState"
    assert session.exec(select(User)).first() is None


def test_oauth_callback_exchange_failure(make_client, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _google_client(make_client)
    client.get("/api/auth/oauth/google/start", follow_redirects=False)
    state = client.cookies.get("pysplit_oauth_state")
    _stub_exchange(monkeypatch, None)

    response = client.get(
        f"/api/auth/oauth/google/callback?code=code&state={state}",
        follow_redirects=False,
    )
    assert response.headers["location"] == "/groups?error=OAuthExchangeFailed"


def test_oauth_callback_links_existing_email(
    make_client, session, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = make_user(
        session,
        email="ada@example.com",
        name="Ada",
        tier=UserTier.GROUP_CREATORS,
    )
    client = _google_client(make_client)
    client.get("/api/auth/oauth/google/start", follow_redirects=False)
    state = client.cookies.get("pysplit_oauth_state")
    _stub_exchange(
        monkeypatch,
        OAuthProfile(
            provider="google",
            provider_account_id="google-ada",
            name="Ada Lovelace",
            email="Ada@Example.com",
            image=None,
        ),
    )

    response = client.get(
        f"/api/auth/oauth/google/callback?code=code&state={state}",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert session.exec(select(User)).all() == [existing]
    session.refresh(existing)
    assert existing.tier == "group_creators"
    assert existing.name == "Ada Lovelace"
    account = session.exec(select(Account)).one()
    assert account.user_id == existing.id


def test_oauth_exchange_google_with_mock_transport() -> None:
    settings = Settings(auth_google_id="id", auth_google_secret="secret", _env_file=None)

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == oauth.GOOGLE_TOKEN_URL:
            return httpx.Response(200, json={"access_token": "access"})
        if str(request.url) == oauth.GOOGLE_USERINFO_URL:
            return httpx.Response(
                200,
                json={
                    "sub": "123",
                    "name": "Ada",
                    "email": "ada@example.com",
                    "picture": "https://example.com/a.png",
                },
            )
        return httpx.Response(404)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await oauth.exchange_oauth_code(
                "google",
                code="code",
                redirect_uri="http://testserver/api/auth/oauth/google/callback",
                settings=settings,
                client=client,
            )

    profile = asyncio.run(run())
    assert profile == OAuthProfile(
        provider="google",
        provider_account_id="123",
        name="Ada",
        email="ada@example.com",
        image="https://example.com/a.png",
    )


def test_oauth_exchange_github_falls_back_to_primary_email() -> None:
    settings = Settings(auth_github_id="id", auth_github_secret="secret", _env_file=None)

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == oauth.GITHUB_TOKEN_URL:
            return httpx.Response(200, json={"access_token": "access"})
        if str(request.url) == oauth.GITHUB_USER_URL:
            return httpx.Response(
                200,
                json={
                    "id": 42,
                    "login": "octocat",
                    "name": None,
                    "email": None,
                    "avatar_url": "https://example.com/o.png",
                },
            )
        if str(request.url) == oauth.GITHUB_EMAILS_URL:
            return httpx.Response(
                200,
                json=[
                    {"email": "secondary@example.com", "primary": False},
                    {"email": "primary@example.com", "primary": True},
                ],
            )
        return httpx.Response(404)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await oauth.exchange_oauth_code(
                "github",
                code="code",
                redirect_uri="http://testserver/api/auth/oauth/github/callback",
                settings=settings,
                client=client,
            )

    profile = asyncio.run(run())
    assert profile is not None
    assert profile.provider_account_id == "42"
    assert profile.name == "octocat"
    assert profile.email == "primary@example.com"


# ---------------------------------------------------------------------------
# Development login and rate limiting
# ---------------------------------------------------------------------------


def test_mock_login_dev_only(make_client) -> None:
    production = make_client(
        environment="production",
        jwt_secret="a" * 40,
    )
    response = mock_login(production, email="prod@example.com")
    assert response.status_code == 404


def test_mock_login_assigns_default_and_explicit_tiers(client: TestClient) -> None:
    response = mock_login(client, email="tiered@example.com")
    assert response.status_code == 200
    assert response.json()["user"]["tier"] == "sync_users"

    response = mock_login(
        client,
        email="tiered@example.com",
        tier=UserTier.GROUP_CREATORS,
    )
    assert response.status_code == 200
    assert response.json()["user"]["tier"] == "group_creators"


def test_auth_account_rate_limit(make_client) -> None:
    client = make_client(
        auth_rate_limit_per_minute=100,
        auth_account_rate_limit_per_minute=2,
        auth_rate_limit_window_seconds=60,
    )
    assert mock_login(client, email="limited@example.com").status_code == 200
    for _ in range(2):
        response = client.post("/api/auth/refresh", headers=csrf_headers(client))
        assert response.status_code == 200
    limited = client.post("/api/auth/refresh", headers=csrf_headers(client))
    assert limited.status_code == 429


def test_auth_rate_limit(make_client) -> None:
    client = make_client(
        auth_rate_limit_per_minute=2,
        auth_rate_limit_window_seconds=60,
        auth_google_id="id",
        auth_google_secret="secret",
        base_url="http://testserver",
    )
    assert client.get("/api/auth/oauth/google/start", follow_redirects=False).status_code == 302
    assert client.get("/api/auth/oauth/google/start", follow_redirects=False).status_code == 302
    limited = client.get("/api/auth/oauth/google/start", follow_redirects=False)
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) >= 1
