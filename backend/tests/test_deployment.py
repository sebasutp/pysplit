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
    assert api["environment"]["ENVIRONMENT"] == "${PYSPLIT_ENVIRONMENT:-production}"

    web = services["web"]
    assert web["depends_on"]["api"]["condition"] == "service_healthy"
    assert "${COMPOSE_WEB_PORT:-8080}:8080" in web["ports"]

    backup = services["backup"]
    assert backup["depends_on"]["api"]["condition"] == "service_healthy"
    assert "pysplit_data:/data" in backup["volumes"]
    assert "pysplit_backups:/backups" in backup["volumes"]
    assert backup["healthcheck"]["disable"] is True
    assert backup["entrypoint"] == ["python"]
    assert backup["command"] == ["/app/scripts/backup_loop.py"]
    assert backup["environment"]["DATABASE_URL"] == "${DATABASE_URL:-sqlite:////data/pysplit.db}"
    assert backup["environment"]["UPLOAD_DIR"] == "${UPLOAD_DIR:-/data/uploads}"


def test_api_dockerfile_runs_migrations_one_worker_and_a_non_root_user() -> None:
    dockerfile = _read("Dockerfile.api")
    assert "docker.io/library/python:3.12-slim" in dockerfile
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
    assert "docker.io/nginxinc/nginx-unprivileged:1.29-alpine" in dockerfile
    assert "USER 101" in dockerfile
    assert "EXPOSE 8080" in dockerfile
    assert "frontend/nginx.conf" in dockerfile
    assert "frontend/nginx-security-headers.conf" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    # COPY preserves the checkout's mode. A production checkout made with
    # umask 0077 would otherwise leave these files root:root 0600, which the
    # UID 101 runtime user cannot read.
    assert "chmod 0644 /etc/nginx/conf.d/default.conf" in dockerfile
    assert "chmod -R a+rX /usr/share/nginx/html" in dockerfile
    # The base image already runs as UID 101, so the chmod must be preceded by
    # a switch to root or it fails with "Operation not permitted".
    chmod_at = dockerfile.index("RUN chmod 0755 /etc/nginx/snippets")
    assert dockerfile.index("USER 0") < chmod_at
    assert dockerfile.index("USER 101", chmod_at) > chmod_at


def test_nginx_proxies_api_without_caching_and_supports_deep_links() -> None:
    nginx = _read("frontend/nginx.conf")
    assert "listen 8080;" in nginx
    # The entrypoint cannot add an IPv6 listen on a read-only root filesystem,
    # so an unconditional one would break hosts with IPv6 disabled.
    assert "listen [::]:8080;" not in nginx
    assert "location ^~ /api/" in nginx
    assert "proxy_pass http://pysplit_api;" in nginx
    assert "proxy_set_header X-Forwarded-Proto $scheme;" in nginx
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in nginx
    assert "proxy_add_x_forwarded_for" not in nginx
    assert 'add_header Cache-Control "no-store" always;' in nginx
    assert "location ^~ /assets/" in nginx
    assert "immutable" in nginx
    assert "try_files $uri $uri/ /index.html;" in nginx
    assert "location = /sw.js" in nginx
    assert "location = /pwa-build.json" in nginx
    assert "client_max_body_size 12m;" in nginx
    assert "location = /healthz" in nginx
    # nginx drops parent add_header directives when a location defines its own,
    # so every location with a cache header must include the snippet.
    assert nginx.count("include /etc/nginx/snippets/pysplit-security-headers.conf;") >= 8
    headers = _read("frontend/nginx-security-headers.conf")
    assert 'X-Content-Type-Options "nosniff"' in headers
    assert 'X-Frame-Options "DENY"' in headers
    assert 'Referrer-Policy "strict-origin-when-cross-origin"' in headers
    assert "Permissions-Policy" in headers


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
    assert "COMPOSE_WEB_PORT=8080" in env
    assert "BACKUP_RETENTION_DAYS" in env


def test_production_env_template_keeps_production_guards_active() -> None:
    production = _read(".env.production.example")
    assert "ENVIRONMENT=production" in production
    assert "PYSPLIT_ENVIRONMENT=production" in production
    assert "JWT_SECRET=\n" in production
    assert "COMPOSE_WEB_PORT=8080" in production
    assert "TRUST_FORWARDED_HEADERS=true" in production
    assert "ENABLE_MOCK_LOGIN=false" in production
    assert "BASE_URL=https://" in production
    assert ".env.production.example" in _read(".gitignore")
    # The development template remains valid for ./dev.
    assert "ENVIRONMENT=development" in _read(".env.example")
    assert "cp .env.production.example .env" in _read("docs/runbook-cutover.md")


def test_operational_scripts_exist_and_are_documented() -> None:
    assert (ROOT / "backend/scripts/backup.py").is_file()
    assert (ROOT / "backend/scripts/backup_loop.py").is_file()
    assert (ROOT / "backend/scripts/restore.py").is_file()
    assert (ROOT / "backend/scripts/performance_check.py").is_file()
    assert (ROOT / "frontend/scripts/check-bundle-size.mjs").is_file()

    package = yaml.safe_load(_read("frontend/package.json"))
    assert package["scripts"]["check:bundle"] == "node scripts/check-bundle-size.mjs"

    makefile = _read("Makefile")
    assert "performance:" in makefile
    assert "backup:" in makefile
    assert "restore:" in makefile
