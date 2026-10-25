"""Development HTTPS and split-origin authentication tests.

The development setup usually puts the SPA and API on different HTTPS origins
(for example ``https://5173.test.example.com`` and
``https://8000.test.example.com``). These tests cover the redirect, CORS,
cookie and CSRF behaviour that requires.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from app.core import oauth
from app.core.config import Settings
from app.core.oauth import OAuthProfile
from app.core.validation import safe_return_to
from app.main import create_app
from tests.helpers import csrf_headers, mock_login

API = "https://8000.test.example.com"
SPA = "https://5173.test.example.com"


def _https_oauth_client(make_client, **overrides):
    return make_client(
        auth_google_id="google-id",
        auth_google_secret="google-secret",
        base_url=API,
        frontend_url=SPA,
        **overrides,
    )


def _stub_exchange(monkeypatch: pytest.MonkeyPatch, profile: OAuthProfile | None) -> None:
    async def fake(*_args, **_kwargs):
        return profile

    monkeypatch.setattr(oauth, "exchange_oauth_code", fake)


def _google_redirect_uri(location: str) -> str:
    query = parse_qs(urlsplit(location).query)
    return query["redirect_uri"][0]


def test_every_api_route_is_under_the_api_prefix() -> None:
    app = create_app(Settings(_env_file=None, api_prefix="/api"))
    spec = app.openapi()

    assert spec["paths"]
    assert all(path.startswith("/api/") for path in spec["paths"])
    assert app.docs_url == "/api/docs"
    assert app.openapi_url == "/api/openapi.json"
    assert app.redoc_url == "/api/redoc"


def test_frontend_and_api_origins_are_allowed_automatically() -> None:
    settings = Settings(
        _env_file=None,
        base_url=f"{API}/",
        frontend_url=f"{SPA}/",
    )
    assert settings.base_url == API
    assert settings.frontend_url == SPA
    assert API in settings.allowed_origins_list
    assert SPA in settings.allowed_origins_list


def test_cors_origin_regex_must_compile() -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, cors_origin_regex="[")

    with pytest.raises(ValueError):
        Settings(_env_file=None, frontend_url="5173.test.example.com")

    settings = Settings(
        _env_file=None,
        cors_origin_regex=r"https://\d+\.test\.example\.com",
    )
    assert settings.cors_origin_regex == r"https://\d+\.test\.example\.com"


def test_oauth_start_uses_https_api_origin_and_accepts_frontend_return_to(make_client) -> None:
    client = _https_oauth_client(make_client)
    response = client.get(
        "/api/auth/oauth/google/start",
        params={"return_to": f"{SPA}/groups/trip?tab=expenses"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith(oauth.GOOGLE_AUTHORIZE_URL)
    assert _google_redirect_uri(location) == f"{API}/api/auth/oauth/google/callback"
    assert client.cookies.get("pysplit_oauth_return_to").strip('"') == ("/groups/trip?tab=expenses")

    state_cookie = next(
        cookie
        for cookie in response.headers.get_list("set-cookie")
        if cookie.startswith("pysplit_oauth_state=")
    )
    assert "Secure" in state_cookie


def test_oauth_callback_returns_to_frontend_origin(
    make_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _https_oauth_client(make_client)
    client.get(
        "/api/auth/oauth/google/start",
        params={"return_to": f"{SPA}/groups/trip"},
        follow_redirects=False,
    )
    state = client.cookies.get("pysplit_oauth_state")
    return_to = client.cookies.get("pysplit_oauth_return_to")
    _stub_exchange(
        monkeypatch,
        OAuthProfile(
            provider="google",
            provider_account_id="google-split-origin",
            name="Grace",
            email="grace@example.com",
            image=None,
            email_verified=True,
        ),
    )

    # Secure cookies are not replayed by TestClient over its plain-HTTP base
    # URL, so present the pair the browser would have sent to the HTTPS proxy.
    response = client.get(
        f"/api/auth/oauth/google/callback?code=code&state={state}",
        headers={"Cookie": (f"pysplit_oauth_state={state}; pysplit_oauth_return_to={return_to}")},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == f"{SPA}/groups/trip"
    set_cookies = response.headers.get_list("set-cookie")
    refresh = next(cookie for cookie in set_cookies if cookie.startswith("pysplit_refresh="))
    assert "Secure" in refresh


def test_oauth_errors_redirect_to_frontend(make_client) -> None:
    client = _https_oauth_client(make_client)
    response = client.get(
        "/api/auth/oauth/google/callback?code=code&state=wrong",
        follow_redirects=False,
    )
    assert response.headers["location"] == f"{SPA}/groups?error=InvalidOAuthState"


def test_forwarded_https_is_used_for_redirects_and_cookies(make_client) -> None:
    client = make_client(
        auth_google_id="google-id",
        auth_google_secret="google-secret",
        trust_forwarded_headers=True,
        enable_mock_login=True,
    )
    forwarded = {
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Host": "8000.test.example.com",
    }

    start = client.get(
        "/api/auth/oauth/google/start",
        headers=forwarded,
        follow_redirects=False,
    )
    assert _google_redirect_uri(start.headers["location"]) == (
        "https://8000.test.example.com/api/auth/oauth/google/callback"
    )

    login = client.post(
        "/api/auth/mock-login",
        json={"email": "forwarded@example.com"},
        headers={**forwarded, "Origin": "https://8000.test.example.com"},
    )
    assert login.status_code == 200
    refresh = next(
        cookie
        for cookie in login.headers.get_list("set-cookie")
        if cookie.startswith("pysplit_refresh=")
    )
    assert "Secure" in refresh


def test_cors_preflight_allows_the_frontend_origin(make_client) -> None:
    client = make_client(frontend_url=SPA)
    response = client.options(
        "/api/auth/me",
        headers={
            "Origin": SPA,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == SPA

    denied = client.options(
        "/api/auth/me",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert denied.headers.get("access-control-allow-origin") is None


def test_csrf_token_is_available_without_reading_the_cookie(make_client) -> None:
    client = make_client(frontend_url=SPA, enable_mock_login=True)
    login = mock_login(client, email="csrf@example.com")
    assert login.status_code == 200
    token = login.json()["csrf_token"]
    assert token == client.cookies.get("pysplit_csrf")

    me = client.get("/api/auth/me")
    assert me.json()["csrf_token"] == token

    refreshed = client.post(
        "/api/auth/refresh",
        headers=csrf_headers(client, origin="http://testserver"),
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["csrf_token"] == client.cookies.get("pysplit_csrf")


def test_cross_site_cookie_options_are_applied(make_client) -> None:
    client = make_client(
        base_url=API,
        frontend_url="https://app.example.net",
        cookie_samesite="none",
        cookie_domain=".test.example.com",
        enable_mock_login=True,
    )
    response = mock_login(
        client,
        email="cross-site@example.com",
        origin="https://app.example.net",
    )
    assert response.status_code == 200
    cookies = response.headers.get_list("set-cookie")
    for name in ("pysplit_refresh", "pysplit_csrf"):
        cookie = next(item for item in cookies if item.startswith(f"{name}="))
        assert "SameSite=none" in cookie
        assert "Secure" in cookie

    csrf = next(item for item in cookies if item.startswith("pysplit_csrf="))
    refresh = next(item for item in cookies if item.startswith("pysplit_refresh="))
    assert "Domain=.test.example.com" in csrf
    assert "Domain=" not in refresh


def test_cors_origin_regex_allows_dynamic_dev_ports(make_client) -> None:
    client = make_client(
        cors_origin_regex=r"https://\d+\.test\.example\.com",
        enable_mock_login=True,
    )
    response = mock_login(
        client,
        email="regex@example.com",
        origin="https://9000.test.example.com",
    )
    assert response.status_code == 200

    rejected = mock_login(
        client,
        email="regex@example.com",
        origin="https://evil.example",
    )
    assert rejected.status_code == 403


def test_safe_return_to_allows_configured_origin_only() -> None:
    assert (
        safe_return_to(
            f"{SPA}/groups/abc?x=1#top",
            allowed_origins=(SPA,),
        )
        == "/groups/abc?x=1#top"
    )
    assert safe_return_to("https://evil.example/steal", allowed_origins=(SPA,)) == "/groups"
    assert safe_return_to("//evil.example/steal", allowed_origins=(SPA,)) == "/groups"
