#!/usr/bin/env python3
"""Fail when frontend JSX renders hardcoded user-facing English.

The scan is intentionally conservative: it reports JSX text nodes and literal
``aria-label`` / ``placeholder`` / ``title`` / ``alt`` values that contain
letters but are not produced by i18n. Brand names, URLs, file types, MIME
types, ISO codes, symbols and values marked with ``i18n-ignore`` are allowed.

Run it from the repository root:

    python3 scripts/check_hardcoded_i18n.py

``scripts/check_i18n_keys.py`` also calls this check, so ``make i18n-keys``
covers both key existence and hardcoded UI text.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "frontend" / "src"
SUFFIXES = {".jsx", ".tsx"}

# Text between two JSX tags. Interpolations, attributes, expressions and quotes
# are excluded so ordinary JavaScript comparisons are not treated as UI text.
JSX_TEXT = re.compile(r">\s*([^<>{}'\";=]+?)\s*<", re.DOTALL)
ATTRIBUTE = re.compile(
    r"\b(?:aria-label|placeholder|title|alt)\s*=\s*(?P<quote>['\"])(?P<value>[^'\"{}]+)(?P=quote)"
)

URL = re.compile(r"^(?:https?://|mailto:|/)[^\s]*$", re.IGNORECASE)
FILE_TYPE = re.compile(r"^\.[A-Za-z0-9]{1,6}(?:\s*,\s*\.[A-Za-z0-9]{1,6})*$")
MIME_TYPE = re.compile(r"^[\w.+-]+/[\w.+-]+$")
SYMBOL_ONLY = re.compile(r"^[\W_]+$")
TECHNICAL_TOKEN = re.compile(r"^[A-Z0-9_.+#-]{2,}$")
PROSE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .,!?'’…:–—%$-]*$")

# Values that are neutral in every language. Keep this list small; prefer an
# explicit ``{/* i18n-ignore */}`` marker for one-off legitimate English.
ALLOWED_TEXT = {
    "api",
    "csv",
    "email",
    "eur",
    "github",
    "jpeg",
    "json",
    "jpy",
    "ok",
    "pdf",
    "png",
    "pysplit",
    "spliit",
    "usd",
}


def candidate(text: str) -> str | None:
    """Return cleaned UI text when it looks like English prose."""
    value = " ".join(text.split())
    if not value or not re.search(r"[A-Za-z]", value):
        return None
    if value.casefold() in ALLOWED_TEXT:
        return None
    if URL.fullmatch(value) or FILE_TYPE.fullmatch(value) or MIME_TYPE.fullmatch(value):
        return None
    if SYMBOL_ONLY.fullmatch(value) or TECHNICAL_TOKEN.fullmatch(value):
        return None
    if not PROSE.fullmatch(value):
        return None
    return value


def line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def scan_file(path: Path) -> list[tuple[int, str]]:
    text = path.read_text(encoding="utf-8")
    hits: list[tuple[int, str]] = []

    for match in JSX_TEXT.finditer(text):
        value = candidate(match.group(1))
        if value and len(value.split()) >= 2:
            line = line_of(text, match.start(1))
            if "i18n-ignore" not in text.splitlines()[line - 1]:
                hits.append((line, value))

    for match in ATTRIBUTE.finditer(text):
        value = candidate(match.group("value"))
        if value:
            line = line_of(text, match.start("value"))
            if "i18n-ignore" not in text.splitlines()[line - 1]:
                hits.append((line, value))

    return hits


def source_files() -> list[Path]:
    return sorted(
        path
        for path in SOURCE.rglob("*")
        if path.suffix in SUFFIXES
        and path.is_file()
        and ".test." not in path.name
        and "__tests__" not in path.parts
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="only print failures (used when called from check_i18n_keys.py)",
    )
    args = parser.parse_args(argv)

    failures = 0
    for path in source_files():
        relative = path.relative_to(ROOT).as_posix()
        for line, value in scan_file(path):
            failures += 1
            print(f"{relative}:{line}: hardcoded UI text: {value!r}", file=sys.stderr)

    if failures:
        print(
            f"{failures} hardcoded UI string(s) found. Use t('key', 'default') or add an i18n-ignore marker.",
            file=sys.stderr,
        )
        return 1

    if not args.quiet:
        print(f"OK: no hardcoded UI text found in {len(source_files())} JSX files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
