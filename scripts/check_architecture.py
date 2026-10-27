#!/usr/bin/env python3
"""Repository-wide architecture checks for the migrated stack.

These checks are intentionally boring text/AST scans so they run in CI and
locally without extra dependencies. They enforce the rules in
docs/adr/0001-stack.md and MIGRATION_PLAN.md section 5.5.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

ROUTERS = (
    "groups.py",
    "expenses.py",
    "receipts.py",
    "balances.py",
    "stats.py",
    "activities.py",
    "categories.py",
    "features.py",
    "health.py",
    "sync.py",
    "auth.py",
    "admin.py",
)
PURE_UTILS = (
    "shares.py",
    "balances.py",
    "totals.py",
    "recurrence.py",
    "currency.py",
    "dates.py",
    "receipt_split.py",
    "receipt_extraction.py",
)
REQUIRED_E2E = (
    "group-management.spec.ts",
    "global-balance.spec.ts",
    "core.spec.ts",
    "expense-edit-delete.spec.ts",
    "expense-variants.spec.ts",
    "split-modes.spec.ts",
    "multi-currency.spec.ts",
    "recurrence.spec.ts",
    "stats.spec.ts",
    "stats-breakdown.spec.ts",
    "reimbursements.spec.ts",
    "repayment-currency.spec.ts",
    "active-user.spec.ts",
    "receipts.spec.ts",
    "admin.spec.ts",
    "offline-sync.spec.ts",
    "group-sync.spec.ts",
    "pwa.spec.ts",
    "pwa-offline.spec.ts",
)
FORBIDDEN_FRONTEND = re.compile(
    r"from\s+['\"][^'\"]*services/(?:api|db|outbox|sync)(?:\.js)?['\"]"
)
FRONTEND_SOURCE_DIRS = ("components", "hooks", "pages")


class Checker:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def fail(self, message: str) -> None:
        self.errors.append(message)

    def check_backend_routers(self) -> None:
        for name in ROUTERS:
            path = BACKEND / "app" / "api" / name
            if not path.is_file():
                self.fail(f"missing router {path.relative_to(ROOT)}")
                continue
            source = path.read_text()
            for forbidden in ("app.models", "sqlmodel", "sqlalchemy", "app.core.database"):
                if forbidden in source:
                    self.fail(f"{path.relative_to(ROOT)} imports {forbidden}")

    def check_pure_utils(self) -> None:
        forbidden = (
            "app.models",
            "sqlmodel",
            "sqlalchemy",
            "app.storage",
            "app.core.config",
            "fastapi",
            "httpx",
        )
        for name in PURE_UTILS:
            path = BACKEND / "app" / "utils" / name
            if not path.is_file():
                self.fail(f"missing pure utility {path.relative_to(ROOT)}")
                continue
            source = path.read_text()
            for token in forbidden:
                if token in source:
                    self.fail(f"{path.relative_to(ROOT)} imports {token}")

    def check_frontend_boundaries(self) -> None:
        sources: list[Path] = []
        for directory in FRONTEND_SOURCE_DIRS:
            sources.extend((FRONTEND / "src" / directory).rglob("*"))
        sources.extend([FRONTEND / "src" / "App.jsx", FRONTEND / "src" / "router.jsx"])
        for path in sources:
            if path.suffix not in {".js", ".jsx", ".ts", ".tsx"} or not path.is_file():
                continue
            source = path.read_text()
            if FORBIDDEN_FRONTEND.search(source):
                self.fail(f"{path.relative_to(ROOT)} imports the HTTP/Dexie layer directly")
            if "dangerouslySetInnerHTML" in source:
                self.fail(f"{path.relative_to(ROOT)} uses dangerouslySetInnerHTML")

    def check_repository(self) -> None:
        for name in (
            "contract.js",
            "online.js",
            "local.js",
            "index.js",
            "contract.test.js",
            "local.test.js",
        ):
            path = FRONTEND / "src" / "services" / "repository" / name
            if not path.is_file():
                self.fail(f"missing repository file {path.relative_to(ROOT)}")

    def check_locales(self) -> None:
        directory = FRONTEND / "src" / "locales" / "messages"
        files = sorted(directory.glob("*.json"))
        if len(files) < 35:
            self.fail(f"expected at least 35 locale files, found {len(files)}")
            return

        def flatten(value, prefix=""):
            if not isinstance(value, dict):
                return [prefix]
            keys: list[str] = []
            for key, child in value.items():
                keys.extend(flatten(child, f"{prefix}.{key}" if prefix else key))
            return keys

        base = set(flatten(json.loads((directory / "en-US.json").read_text())))
        for path in files:
            keys = set(flatten(json.loads(path.read_text())))
            missing = sorted(base - keys)
            extra = sorted(keys - base)
            if missing or extra:
                self.fail(
                    f"{path.name} locale key drift: {len(missing)} missing, {len(extra)} extra"
                )

    def check_e2e(self) -> None:
        directory = FRONTEND / "e2e"
        for name in REQUIRED_E2E:
            if not (directory / name).is_file():
                self.fail(f"missing e2e spec {name}")

    def run(self) -> int:
        self.check_backend_routers()
        self.check_pure_utils()
        self.check_frontend_boundaries()
        self.check_repository()
        self.check_locales()
        self.check_e2e()
        if self.errors:
            for error in self.errors:
                print(f"FAIL: {error}", file=sys.stderr)
            print(f"\n{len(self.errors)} architecture error(s).", file=sys.stderr)
            return 1
        print("OK: architecture boundaries, repository files, locales and e2e specs are consistent.")
        return 0


if __name__ == "__main__":
    raise SystemExit(Checker().run())
