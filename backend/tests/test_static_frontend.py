"""The production image serves the compiled SPA from the API process."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

INDEX_HTML = "<!doctype html><html><body><div id='root'>pysplit</div></body></html>"


@pytest.fixture()
def dist(tmp_path: Path) -> Path:
    directory = tmp_path / "dist"
    (directory / "assets").mkdir(parents=True)
    (directory / "icons").mkdir()
    (directory / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (directory / "assets" / "app-abc123.js").write_text("console.log('app')\n", encoding="utf-8")
    (directory / "sw.js").write_text("self.addEventListener('fetch', () => {})\n", encoding="utf-8")
    (directory / "pwa-build.json").write_text('{"buildId":"1"}\n', encoding="utf-8")
    (directory / "manifest.webmanifest").write_text('{"name":"pysplit"}\n', encoding="utf-8")
    (directory / "icons" / "icon-192.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (directory / "favicon.ico").write_bytes(b"ico")
    return directory


def test_serves_the_spa_shell_and_deep_links(make_client, dist: Path) -> None:
    client: TestClient = make_client(frontend_dist_dir=str(dist))

    root = client.get("/")
    assert root.status_code == 200
    assert INDEX_HTML in root.text
    assert root.headers["cache-control"] == "no-cache"

    deep_link = client.get("/groups/abc123")
    assert deep_link.status_code == 200
    assert INDEX_HTML in deep_link.text
    assert deep_link.headers["cache-control"] == "no-cache"

    # Browser hardening previously supplied by nginx now applies to every
    # response, including the SPA shell.
    assert root.headers["x-content-type-options"] == "nosniff"
    assert root.headers["x-frame-options"] == "DENY"
    assert root.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "camera=(self)" in root.headers["permissions-policy"]


def test_hashed_assets_and_media_get_long_lived_cache_headers(make_client, dist: Path) -> None:
    client: TestClient = make_client(frontend_dist_dir=str(dist))

    asset = client.get("/assets/app-abc123.js")
    assert asset.status_code == 200
    assert "console.log" in asset.text
    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"

    icon = client.get("/icons/icon-192.png")
    assert icon.status_code == 200
    assert icon.headers["cache-control"] == "public, max-age=2592000"

    favicon = client.get("/favicon.ico")
    assert favicon.status_code == 200
    assert favicon.headers["cache-control"] == "public, max-age=2592000"


def test_service_worker_manifest_and_build_contract_are_revalidated(
    make_client, dist: Path
) -> None:
    client: TestClient = make_client(frontend_dist_dir=str(dist))

    for path in ("/sw.js", "/pwa-build.json"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-cache, no-store, must-revalidate"

    manifest = client.get("/manifest.webmanifest")
    assert manifest.status_code == 200
    assert manifest.headers["cache-control"] == "no-cache"


def test_api_responses_are_not_cached_or_replaced_by_the_spa(make_client, dist: Path) -> None:
    client: TestClient = make_client(frontend_dist_dir=str(dist))

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.headers["cache-control"] == "no-store"
    assert health.headers["x-content-type-options"] == "nosniff"

    for path in ("/api/not-a-route", "/api"):
        missing = client.get(path)
        assert missing.status_code == 404
        assert "application/json" in missing.headers["content-type"]
        assert INDEX_HTML not in missing.text


def test_missing_static_files_are_real_404s(make_client, dist: Path) -> None:
    client: TestClient = make_client(frontend_dist_dir=str(dist))

    for path in ("/assets/missing.js", "/missing.png", "/workbox-missing.js"):
        response = client.get(path)
        assert response.status_code == 404
        assert INDEX_HTML not in response.text


def test_missing_frontend_directory_fails_at_startup(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, frontend_dist_dir=str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="FRONTEND_DIST_DIR does not exist"):
        create_app(settings)
