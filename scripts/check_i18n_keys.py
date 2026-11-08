#!/usr/bin/env python3
"""Fail when frontend source uses an i18n key that is missing from en-US.

The check scans ``frontend/src`` for:

* static calls such as ``t('Groups.myGroups')`` / ``t("...")``, including
  calls whose key is on the next line,
* ``i18nKey="..."`` / ``i18nKey='...'`` props (react-i18next ``<Trans>``),
* template-literal calls such as ``t(`Theme.${value}`)``.  Every dynamic
  family must be listed in ``frontend/src/locales/dynamic-families.json`` so
  the check knows the concrete keys the template can produce; an unknown family
  fails the check instead of being silently skipped. The frontend test
  ``services/i18n-quality.test.js`` compares that file with the real option
  arrays.

Keys are compared with the flattened ``en-US`` catalogue, which is the source
of truth for the other locales as well. The same run also checks JSX for
hardcoded user-facing English through ``check_hardcoded_i18n.py``.  Run it from the repository root:

    python3 scripts/check_i18n_keys.py

or through ``make i18n-keys``.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
SOURCE = FRONTEND / "src"
CATALOGUE = SOURCE / "locales" / "messages" / "en-US.json"
SOURCE_SUFFIXES = {".js", ".jsx", ".ts", ".tsx"}

# Keys produced by template-literal ``t(`prefix.${value}`)`` calls. The
# concrete values live in a shared JSON file so the frontend test can compare
# them with the actual option arrays. Adding a new option without adding its
# key to en-US fails both checks.
DYNAMIC_FAMILIES_PATH = SOURCE / "locales" / "dynamic-families.json"
DYNAMIC_FAMILIES = {
    prefix: tuple(suffixes)
    for prefix, suffixes in json.loads(
        DYNAMIC_FAMILIES_PATH.read_text(encoding="utf-8")
    ).items()
}

STATIC_CALL = re.compile(r"\bt\(\s*(['\"])(?P<key>[^'\"]+)\1")
I18N_KEY_PROP = re.compile(r"\bi18nKey\s*=\s*(['\"])(?P<key>[^'\"]+)\1")
DYNAMIC_CALL = re.compile(r"\bt\(\s*`(?P<template>[^`]*\$\{[^`]*)`")


def flatten(value: dict, prefix: str = "") -> list[str]:
    keys: list[str] = []
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(child, dict):
            keys.extend(flatten(child, path))
        else:
            keys.append(path)
    return keys


def source_files() -> list[Path]:
    return sorted(
        path
        for path in SOURCE.rglob("*")
        if path.suffix in SOURCE_SUFFIXES
        and path.is_file()
        and ".test." not in path.name
        and "__tests__" not in path.parts
    )


def dynamic_prefix(template: str) -> str:
    """Return the literal prefix of a template-literal key."""
    return template.split("${", 1)[0]


def collect() -> tuple[set[str], dict[str, list[str]]]:
    """Return used keys and ``{file: [unknown dynamic families]}``."""
    used: set[str] = set()
    unknown: dict[str, list[str]] = {}
    for path in source_files():
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT).as_posix()
        for match in STATIC_CALL.finditer(text):
            used.add(match.group("key"))
        for match in I18N_KEY_PROP.finditer(text):
            used.add(match.group("key"))
        for match in DYNAMIC_CALL.finditer(text):
            template = match.group("template")
            prefix = dynamic_prefix(template)
            suffixes = DYNAMIC_FAMILIES.get(prefix)
            if suffixes is None:
                unknown.setdefault(relative, []).append(template)
                continue
            for suffix in suffixes:
                used.add(f"{prefix}{suffix}")
    return used, unknown


def main() -> int:
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    available = set(flatten(catalogue))
    used, unknown = collect()
    missing = sorted(used - available)

    failed = False
    if unknown:
        failed = True
        print("Unknown dynamic i18n key families:", file=sys.stderr)
        for path, templates in sorted(unknown.items()):
            for template in templates:
                print(f"  {path}: t(`{template}`)", file=sys.stderr)
        print(
            "Add the family to frontend/src/locales/dynamic-families.json.",
            file=sys.stderr,
        )

    if missing:
        failed = True
        print(f"{len(missing)} used i18n key(s) missing from en-US:", file=sys.stderr)
        for key in missing:
            print(f"  {key}", file=sys.stderr)

    try:
        from check_hardcoded_i18n import main as hardcoded_main
    except ImportError:  # pragma: no cover - running as a package module
        from scripts.check_hardcoded_i18n import main as hardcoded_main

    if hardcoded_main(["--quiet"]) != 0:
        failed = True

    if failed:
        return 1

    print(
        f"OK: {len(used)} used i18n keys are all present in "
        f"{CATALOGUE.relative_to(ROOT).as_posix()}."
    )
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
