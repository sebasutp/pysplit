"""Repository invariants that support operator-provided deployments."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


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
    # The backend can serve a compiled SPA; deployment packaging is operator-owned.
    assert "FRONTEND_DIST_DIR=frontend/dist" in env


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
