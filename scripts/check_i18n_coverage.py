#!/usr/bin/env python3
"""Report how many source-used i18n keys each locale actually translates.

The numerator counts keys whose locale value is a non-empty string that differs
from en-US and keeps the same placeholder/HTML-tag signature. Values that are
language-neutral (brand names, acronyms, file types, placeholders, numeric
symbols and a few example participant names) count as translated too, so a
locale is not penalised for leaving ``JSON`` or ``{count}`` unchanged.

Missing keys, empty/non-string values and signature mismatches never count as
translated. They are listed in the report, and any gating mode (``--min``,
``--baseline`` or ``--strict``) exits nonzero when they are present.

Only keys that ``check_i18n_keys.collect`` finds in the frontend source are
reported; stale catalogue entries do not inflate the score. The command is
report-only by default so it can be adopted without breaking CI. Pass ``--min``
or ``--baseline`` to turn the report into a coverage gate, and ``--strict`` to
also reject every non-allowlisted value that still equals en-US:

    python3 scripts/check_i18n_coverage.py
    python3 scripts/check_i18n_coverage.py --min 70
    python3 scripts/check_i18n_coverage.py --baseline i18n-baseline.json
    python3 scripts/check_i18n_coverage.py --strict
    python3 scripts/check_i18n_coverage.py --allowlist i18n-allowlist.json

``--allowlist`` takes a JSON object mapping message keys (``fnmatch`` patterns
such as ``"GroupForm.*.name"`` are supported) to a non-empty reason. A bare
list is rejected because it has no reasons:

    {"Homepage.button.github": "brand name"}

Run it from the repository root or through ``make i18n-coverage``.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:  # Running as a script puts scripts/ on sys.path.
    from check_i18n_keys import collect
except ImportError:  # pragma: no cover - running as a package module
    from scripts.check_i18n_keys import collect

ROOT = Path(__file__).resolve().parents[1]
CATALOGUES = ROOT / "frontend" / "src" / "locales" / "messages"
BASE_LOCALE = "en-US"

# Values that are identical in every language by design. Keep this list small;
# add genuinely neutral values with --allowlist when they need an explanation.
NEUTRAL_VALUES = {
    "pysplit",
    "spliit",
    "github",
    "json",
    "csv",
    "pdf",
    "url",
    "api",
}
NEUTRAL_KEYS = {
    "Homepage.button.github": "brand name",
    "GroupForm.Participants.John": "example participant name",
    "GroupForm.Participants.Jane": "example participant name",
    "GroupForm.Participants.Jack": "example participant name",
}

SYMBOL_ONLY = re.compile(r"^[\W_]+$")
PLACEHOLDER_ONLY = re.compile(r"^(?:\{\{?\s*[\w.]+\s*\}?\}\s*)+$")
FILE_TYPE = re.compile(r"^\.[A-Za-z0-9]{1,6}(?:\s*,\s*\.[A-Za-z0-9]{1,6})*$")
MIME_TYPE = re.compile(r"^[\w.+-]+/[\w.+-]+$")
NUMERIC = re.compile(r"^[\d\s.,%+\-\u2013\u2014/\u00d7x*]+$")
# Keep in step with frontend/scripts/sync-locales.mjs: interpolation tokens and
# HTML/markup tags must survive translation unchanged.
SIGNATURE_TOKEN = re.compile(r"\{\{?[^}]+\}?\}|</?[a-z][^>]*>", re.IGNORECASE)


@dataclass
class LocaleCoverage:
    """Coverage counters and the problems found in one locale catalogue."""

    translated: int
    total: int
    neutral: int
    missing: list[str] = field(default_factory=list)
    empty: list[str] = field(default_factory=list)
    signature_mismatch: list[str] = field(default_factory=list)
    english: list[str] = field(default_factory=list)

    @property
    def percent(self) -> float:
        return self.translated / self.total * 100 if self.total else 0.0


def flatten(value: object, prefix: str = "") -> dict[str, object]:
    """Flatten a nested message catalogue to ``{ "a.b.c": leaf }``."""
    if not isinstance(value, dict):
        return {prefix: value}
    flattened: dict[str, object] = {}
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else key
        flattened.update(flatten(child, path))
    return flattened


def signature(value: object) -> tuple[str, ...]:
    """Return the sorted interpolation/HTML-tag signature of a message."""
    if not isinstance(value, str):
        return ()
    return tuple(sorted(token.casefold() for token in SIGNATURE_TOKEN.findall(value)))


def load_allowlist(path: Path | None) -> dict[str, str]:
    """Load a ``{key-or-pattern: reason}`` allowlist.

    Every entry needs a real reason; a bare list is rejected so the gate cannot
    silently ignore English text without an explanation.
    """
    if path is None:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise SystemExit(f"Cannot read allowlist {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise SystemExit(f"Invalid JSON in allowlist {path}: {error}") from error

    if isinstance(data, list):
        raise SystemExit(
            f"Allowlist {path} must map keys to reasons; a bare list has no reasons."
        )
    if not isinstance(data, dict):
        raise SystemExit(f"Allowlist {path} must contain a JSON object.")

    entries = data.get("keys", data)
    if not isinstance(entries, dict):
        raise SystemExit(f"Allowlist {path} 'keys' entry must be a JSON object.")

    reasons: dict[str, str] = {}
    for pattern, reason in entries.items():
        if not isinstance(reason, str) or not reason.strip():
            raise SystemExit(
                f"Allowlist entry {pattern!r} in {path} needs a non-empty reason."
            )
        reasons[str(pattern)] = reason.strip()
    return reasons


def is_neutral(
    key: str, value: object, allowlist: dict[str, str] | None = None
) -> bool:
    """Return True when an English value does not need translating."""
    if key in NEUTRAL_KEYS:
        return True
    for pattern in allowlist or {}:
        if fnmatch.fnmatchcase(key, pattern):
            return True
    if not isinstance(value, str):
        return False

    text = value.strip()
    if text.casefold() in NEUTRAL_VALUES:
        return True
    return bool(
        SYMBOL_ONLY.fullmatch(text)
        or PLACEHOLDER_ONLY.fullmatch(text)
        or FILE_TYPE.fullmatch(text)
        or MIME_TYPE.fullmatch(text)
        or NUMERIC.fullmatch(text)
    )


def coverage(
    used: set[str],
    base: dict[str, object],
    locale: dict[str, object],
    allowlist: dict[str, str] | None = None,
) -> LocaleCoverage:
    """Return coverage counters and problems for one locale."""
    report = LocaleCoverage(translated=0, total=len(used), neutral=0)
    for key in used:
        base_value = base.get(key)
        if key not in locale:
            report.missing.append(key)
            continue

        value = locale[key]
        if not isinstance(value, str) or not value.strip():
            report.empty.append(key)
            continue

        if value != base_value:
            if signature(value) != signature(base_value):
                report.signature_mismatch.append(key)
            else:
                report.translated += 1
        elif is_neutral(key, base_value, allowlist):
            report.translated += 1
            report.neutral += 1
        else:
            report.english.append(key)
    return report


def parse_percent(value: object, locale: str, path: Path) -> float:
    """Accept a number, a percentage string, or ``{"percent": ...}``."""
    if isinstance(value, dict):
        for field in ("percent", "coverage", "min"):
            if field in value:
                return parse_percent(value[field], locale, path)
        raise SystemExit(f"Baseline entry for {locale} in {path} has no percent.")
    if isinstance(value, str):
        value = value.strip().removesuffix("%")
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise SystemExit(
            f"Baseline percentage for {locale} in {path} is not a number: {value!r}"
        ) from error


def load_baseline(path: Path) -> dict[str, float]:
    """Load ``{locale: percent}`` (optionally wrapped in ``{"locales": ...}``)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise SystemExit(f"Cannot read baseline {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise SystemExit(f"Invalid JSON in baseline {path}: {error}") from error

    if isinstance(data, dict) and isinstance(data.get("locales"), dict):
        data = data["locales"]
    if not isinstance(data, dict):
        raise SystemExit(f"Baseline {path} must contain a JSON object.")
    return {
        str(locale): parse_percent(value, str(locale), path)
        for locale, value in data.items()
    }


def key_sample(keys: list[str], limit: int = 5) -> str:
    """Return a short comma-separated key sample for failure messages."""
    sample = ", ".join(sorted(keys)[:limit])
    return f"{sample}, ..." if len(keys) > limit else sample


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--min",
        type=float,
        metavar="PERCENT",
        help="exit nonzero when any locale is below this coverage",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        metavar="FILE",
        help="JSON {locale: percent} baseline; fail if a locale regresses",
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        metavar="FILE",
        help="JSON {key-or-pattern: reason} of values that may stay English",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "fail on missing/empty values, signature mismatches and every "
            "non-allowlisted value that still equals en-US"
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.min is not None and not 0 <= args.min <= 100:
        raise SystemExit("--min must be between 0 and 100.")

    used, unknown = collect()
    if unknown:
        print(
            "Warning: unknown dynamic i18n key families; coverage may be incomplete.",
            file=sys.stderr,
        )

    try:
        base = flatten(json.loads((CATALOGUES / f"{BASE_LOCALE}.json").read_text()))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Cannot read en-US catalogue: {error}") from error

    missing_from_base = sorted(used - base.keys())
    if missing_from_base:
        print(
            f"Warning: {len(missing_from_base)} used key(s) are missing from en-US; "
            "they count as untranslated.",
            file=sys.stderr,
        )

    allowlist = load_allowlist(args.allowlist)
    baseline = load_baseline(args.baseline) if args.baseline else {}
    support_files = {
        path.resolve() for path in (args.baseline, args.allowlist) if path is not None
    }

    reports: list[tuple[str, LocaleCoverage]] = []
    for path in sorted(CATALOGUES.glob("*.json")):
        locale = path.stem
        if locale == BASE_LOCALE or path.resolve() in support_files:
            continue
        try:
            catalogue = flatten(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as error:
            raise SystemExit(f"Cannot read {path.name}: {error}") from error
        reports.append((locale, coverage(used, base, catalogue, allowlist)))

    width = max((len(locale) for locale, _report in reports), default=len("Locale"))
    print(
        f"{'Locale'.ljust(width)}  {'Translated / Used':>18}  Coverage  "
        f"{'Neutral':>7}  {'English':>7}  {'Empty':>5}  {'Sig':>3}"
    )
    print(
        f"{'-' * width}  {'-' * 18}  --------  {'-' * 7}  {'-' * 7}  {'-' * 5}  {'-' * 3}"
    )
    for locale, report in reports:
        invalid = len(report.missing) + len(report.empty)
        print(
            f"{locale.ljust(width)}  {f'{report.translated} / {report.total}':>18}  "
            f"{report.percent:7.1f}%  {report.neutral:^7}  {len(report.english):^7}  "
            f"{invalid:^5}  {len(report.signature_mismatch):^3}"
        )

    failures: list[str] = []
    if args.min is not None:
        failures.extend(
            f"{locale} {report.percent:.1f}% is below --min {args.min:g}%"
            for locale, report in reports
            if report.percent + 1e-9 < args.min
        )

    if baseline:
        known = {locale for locale, _report in reports}
        for locale in sorted(baseline.keys() - known):
            print(
                f"Warning: baseline locale {locale} has no catalogue.", file=sys.stderr
            )
        failures.extend(
            f"{locale} {report.percent:.1f}% is below baseline {baseline[locale]:g}%"
            for locale, report in reports
            if locale in baseline and report.percent + 1e-9 < baseline[locale]
        )

    # Any gating mode rejects values that are structurally invalid. --strict
    # additionally requires every non-allowlisted value to differ from en-US.
    if args.strict or args.min is not None or baseline:
        for locale, report in reports:
            if report.missing:
                failures.append(
                    f"{locale} is missing {len(report.missing)} used key(s): "
                    f"{key_sample(report.missing)}"
                )
            if report.empty:
                failures.append(
                    f"{locale} has {len(report.empty)} empty/non-string used value(s): "
                    f"{key_sample(report.empty)}"
                )
            if report.signature_mismatch:
                failures.append(
                    f"{locale} has {len(report.signature_mismatch)} placeholder/markup "
                    f"signature mismatch(es): {key_sample(report.signature_mismatch)}"
                )
            if args.strict and report.english:
                failures.append(
                    f"{locale} has {len(report.english)} non-allowlisted value(s) still "
                    f"equal to en-US: {key_sample(report.english)}"
                )

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    if args.strict:
        print("OK: every checked locale is fully and safely translated.")
    elif args.min is not None or baseline:
        print("OK: every checked locale meets its coverage floor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
