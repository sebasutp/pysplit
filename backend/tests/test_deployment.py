"""Stage 12: production deployment assets stay consistent with the code."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_compose_defines_api_web_and_optional_backup() -> None:
    compose = yaml.safe_load(_read("compose.yaml"))
    services = compose["services"]
    assert set(services) == {"api", "web", "backup"}
    assert services["backup"]["profiles"] == ["backup"]

    api = services["api"]
    assert "ports" not in api, "the API must only be reachable through nginx"
    assert "pysplit_data:/data" in api["volumes"]
    assert api["healthcheck"]["test"]
    assert api["environment"]["ENABLE_MOCK_LOGIN"] == "false"
    assert api["environment"]["ENVIRONMENT"] == "${ENVIRONMENT:-production}"

    web = services["web"]
    assert web["depends_on"]["api"]["condition"] == "service_healthy"
    assert "${WEB_PORT:-8080}:80" in web["ports"]

    backup = services["backup"]
    assert "pysplit_data:/data:ro" in backup["volumes"]
    assert any("scripts/backup.py" in line for line in backup["command"])


def test_api_dockerfile_runs_migrations_one_worker_and_a_non_root_user() -> None:
    dockerfile = _read("Dockerfile.api")
    assert "python:3.12-slim" in dockerfile
    assert "alembic upgrade head" in _read("backend/docker-entrypoint.sh")
    assert "--workers 1" in _read("backend/docker-entrypoint.sh")
    assert "--no-proxy-headers" in _read("backend/docker-entrypoint.sh")
    assert "USER app" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "/data" in dockerfile


def test_web_dockerfile_builds_the_spa_and_serves_it_with_nginx() -> None:
    dockerfile = _read("Dockerfile.web")
    assert "npm ci" in dockerfile
    assert "npm run build" in dockerfile
    assert "nginx:1.29-alpine" in dockerfile
    assert "frontend/nginx.conf" in dockerfile
    assert "HEALTHCHECK" in dockerfile


def test_nginx_proxies_api_without_caching_and_supports_deep_links() -> None:
    nginx = _read("frontend/nginx.conf")
    assert "location /api/" in nginx
    assert "proxy_pass http://pysplit_api;" in nginx
    assert "proxy_set_header X-Forwarded-Proto $scheme;" in nginx
    assert 'add_header Cache-Control "no-store" always;' in nginx
    assert "location /assets/" in nginx
    assert "immutable" in nginx
    assert "try_files $uri $uri/ /index.html;" in nginx
    assert "location = /sw.js" in nginx
    assert "location = /pwa-build.json" in nginx
    assert "client_max_body_size 12m;" in nginx
    assert "location = /healthz" in nginx


def test_dockerignore_protects_secrets_data_and_dependencies() -> None:
    ignored = _read(".dockerignore")
    for pattern in (".env", "data", "backend/data", "frontend/node_modules", "spliit"):
        assert pattern in ignored.splitlines()
    assert "backend/requirements.txt" not in ignored.splitlines()
    assert "backend/alembic" not in ignored.splitlines()


def test_env_example_documents_every_setting() -> None:
    tree = ast.parse(_read("backend/app/core/config.py"))
    fields: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Settings":
            for statement in node.body:
                if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
                    fields.append(statement.target.id.upper())
    env = _read(".env.example")
    documented = set(re.findall(r"^#? ?([A-Z][A-Z0-9_]*)=", env, re.MULTILINE))
    assert not [field for field in fields if field not in documented]
    assert "JWT_SECRET" in env
    assert "BASE_URL" in env
    assert "LOG_FORMAT=json" in env
    assert "WEB_PORT=8080" in env
    assert "BACKUP_RETENTION_DAYS" in env


def test_operational_scripts_exist_and_are_documented() -> None:
    assert (ROOT / "backend/scripts/backup.py").is_file()
    assert (ROOT / "backend/scripts/restore.py").is_file()
    assert (ROOT / "backend/scripts/performance_check.py").is_file()
    assert (ROOT / "frontend/scripts/check-bundle-size.mjs").is_file()

    package = yaml.safe_load(_read("frontend/package.json"))
    assert package["scripts"]["check:bundle"] == "node scripts/check-bundle-size.mjs"

    makefile = _read("Makefile")
    assert "performance:" in makefile
    assert "backup:" in makefile
    assert "restore:" in makefile
