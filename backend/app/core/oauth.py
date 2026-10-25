"""Google and GitHub OAuth.

Only the two providers supported by the reference fork are implemented. The
authorization URL builders are pure functions so provider discovery and URL
shape can be tested without network access; the exchange functions accept an
optional ``httpx.AsyncClient`` so tests can inject a mock transport.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.core.config import Settings

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"

SUPPORTED_PROVIDERS = ("google", "github")
_HTTP_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class OAuthProfile:
    provider: str
    provider_account_id: str
    name: str | None
    email: str | None
    image: str | None
    email_verified: bool | None = None


def _clean(value: str | None) -> str:
    if not value:
        return ""
    return value.strip().strip("\"'")


def _credentials(provider: str, settings: Settings) -> tuple[str, str] | None:
    if provider == "google":
        client_id = _clean(settings.auth_google_id)
        client_secret = _clean(settings.auth_google_secret)
    elif provider == "github":
        client_id = _clean(settings.auth_github_id)
        client_secret = _clean(settings.auth_github_secret)
    else:
        return None
    if not client_id or not client_secret:
        return None
    return client_id, client_secret


def provider_enabled(provider: str, settings: Settings) -> bool:
    return provider in SUPPORTED_PROVIDERS and _credentials(provider, settings) is not None


def get_authorization_url(
    provider: str,
    *,
    state: str,
    redirect_uri: str,
    settings: Settings,
) -> str | None:
    """Build the provider authorization URL, or ``None`` when unavailable."""
    credentials = _credentials(provider, settings)
    if credentials is None:
        return None
    client_id, _ = credentials

    if provider == "google":
        query = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "access_type": "online",
                "prompt": "select_account",
            }
        )
        return f"{GOOGLE_AUTHORIZE_URL}?{query}"

    if provider == "github":
        query = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": "read:user user:email",
                "state": state,
            }
        )
        return f"{GITHUB_AUTHORIZE_URL}?{query}"

    return None


async def _json(response: httpx.Response) -> dict:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


async def exchange_oauth_code(
    provider: str,
    *,
    code: str,
    redirect_uri: str,
    settings: Settings,
    client: httpx.AsyncClient | None = None,
) -> OAuthProfile | None:
    """Exchange an authorization code for a verified provider profile."""
    credentials = _credentials(provider, settings)
    if credentials is None or not code:
        return None
    client_id, client_secret = credentials

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS)

    try:
        if provider == "google":
            return await _exchange_google(client, code, redirect_uri, client_id, client_secret)
        if provider == "github":
            return await _exchange_github(client, code, redirect_uri, client_id, client_secret)
        return None
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return None
    finally:
        if owns_client:
            await client.aclose()


async def _exchange_google(
    client: httpx.AsyncClient,
    code: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str,
) -> OAuthProfile | None:
    token_response = await client.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if token_response.status_code >= 400:
        return None
    tokens = await _json(token_response)
    access_token = tokens.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        return None

    profile_response = await client.get(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if profile_response.status_code >= 400:
        return None
    profile = await _json(profile_response)
    subject = profile.get("sub")
    if subject is None:
        return None
    return OAuthProfile(
        provider="google",
        provider_account_id=str(subject),
        name=profile.get("name") if isinstance(profile.get("name"), str) else None,
        email=profile.get("email") if isinstance(profile.get("email"), str) else None,
        image=profile.get("picture") if isinstance(profile.get("picture"), str) else None,
        email_verified=profile.get("email_verified") is True,
    )


async def _exchange_github(
    client: httpx.AsyncClient,
    code: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str,
) -> OAuthProfile | None:
    token_response = await client.post(
        GITHUB_TOKEN_URL,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        },
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    if token_response.status_code >= 400:
        return None
    tokens = await _json(token_response)
    access_token = tokens.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        return None

    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "pysplit",
        "Accept": "application/vnd.github+json",
    }
    profile_response = await client.get(GITHUB_USER_URL, headers=headers)
    if profile_response.status_code >= 400:
        return None
    profile = await _json(profile_response)
    subject = profile.get("id")
    if subject is None:
        return None

    # Always consult the dedicated emails endpoint: the profile's public email
    # is not proof that the address belongs to (or is verified by) this user.
    email: str | None = None
    email_verified: bool | None = None
    emails_response = await client.get(GITHUB_EMAILS_URL, headers=headers)
    if emails_response.status_code < 400:
        emails = emails_response.json()
        if isinstance(emails, list):
            candidate = next(
                (
                    entry
                    for entry in emails
                    if isinstance(entry, dict)
                    and entry.get("primary") is True
                    and entry.get("verified") is True
                ),
                None,
            )
            if candidate and isinstance(candidate.get("email"), str):
                email = candidate["email"]
                email_verified = True

    name = profile.get("name")
    if not isinstance(name, str) or not name:
        login = profile.get("login")
        name = login if isinstance(login, str) else None
    image = profile.get("avatar_url")
    return OAuthProfile(
        provider="github",
        provider_account_id=str(subject),
        name=name if isinstance(name, str) else None,
        email=email,
        image=image if isinstance(image, str) else None,
        email_verified=email_verified,
    )
