#!/usr/bin/env python3
"""Fill the remaining used-key translations in the app locale catalogues.

The pipeline is deliberately conservative:

1. Keys that are still English are first matched against the upstream Spliit
   catalogues by *English value*. When an upstream locale has a real human
   translation for the same source string (and the same placeholder set) that
   translation is reused.
2. Remaining strings are machine translated with the public Google Translate
   endpoint. Placeholders and HTML tags are replaced with sentinel tokens before
   the request and restored verbatim afterwards, so interpolation keeps working.
3. A small glossary supplies context-aware terms (receipt line items, merchant,
   printed total, …) and per-locale overrides for the most visible receipt
   vocabulary. Values that are language-neutral (brand names, acronyms, file
   types, symbols) are never sent for translation.

Only used keys that are currently identical to en-US are touched; existing
human translations and unused catalogue entries are preserved. Output keeps the
en-US key order, two-space indentation and a trailing newline.

Usage:
    python3 scripts/translate_locales.py --dry-run
    python3 scripts/translate_locales.py --locales de-DE,fr-FR
    python3 scripts/translate_locales.py --report

The HTTP cache defaults to ``/tmp/pysplit-i18n-cache.json`` so repeated runs
are cheap and idempotent. Pass ``--no-cache`` to start fresh.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

try:  # Running as a script puts scripts/ on sys.path.
    from check_i18n_coverage import flatten, is_neutral
    from check_i18n_keys import collect
except ImportError:  # pragma: no cover - running as a package module
    from scripts.check_i18n_coverage import flatten, is_neutral
    from scripts.check_i18n_keys import collect

ROOT = Path(__file__).resolve().parents[1]
CATALOGUES = ROOT / "frontend" / "src" / "locales" / "messages"
UPSTREAM = Path(os.environ.get("SPLIIT_MESSAGES_DIR", "/tmp/upstream"))
GLOSSARY_PATH = Path(__file__).with_name("i18n-glossary.json")
BASE_LOCALE = "en-US"
ENDPOINT = "https://translate.googleapis.com/translate_a/single"
BATCH_SEPARATOR = "\n@@@\n"
SENTINEL = "\u27e6PH{}\u27e7"
SENTINEL_RE = re.compile(r"\u27e6PH(\d+)\u27e7")

# Locale code sent to Google Translate. The app uses region-qualified tags for
# some languages; the endpoint accepts those as well.
LANGUAGE_CODE = {
    "cs-CZ": "cs",
    "de-DE": "de",
    "fr-FR": "fr",
    "it-IT": "it",
    "ja-JP": "ja",
    "nl-NL": "nl",
    "pl-PL": "pl",
    "pt-BR": "pt-BR",
    "ru-RU": "ru",
    "tr-TR": "tr",
    "uk-UA": "uk",
    "zh-CN": "zh-CN",
    "zh-TW": "zh-TW",
}


def language_code(locale: str) -> str:
    return LANGUAGE_CODE.get(locale, locale.split("-")[0])


def normalise(text: str) -> str:
    """Normalise whitespace for source-value matching only."""
    return " ".join(text.split())


def extract_placeholders(text: str) -> list[str]:
    """Return balanced ``{...}`` placeholders and HTML tags in source order."""
    tokens: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == "{":
            depth = 0
            end = index
            while end < length:
                if text[end] == "{":
                    depth += 1
                elif text[end] == "}":
                    depth -= 1
                    if depth == 0:
                        end += 1
                        break
                end += 1
            if depth != 0:
                index += 1
                continue
            tokens.append(text[index:end])
            index = end
            continue
        if char == "<":
            match = re.match(r"</?[A-Za-z][^>]*>", text[index:])
            if match:
                tokens.append(match.group(0))
                index += len(match.group(0))
                continue
        index += 1
    return tokens


def protect(text: str) -> tuple[str, list[str]]:
    """Replace placeholders and HTML tags with stable sentinel tokens."""
    tokens = extract_placeholders(text)
    if not tokens:
        return text, []

    result: list[str] = []
    cursor = 0
    for position, token in enumerate(tokens):
        start = text.find(token, cursor)
        if start < 0:  # pragma: no cover - extract_placeholders guarantees it
            continue
        result.append(text[cursor:start])
        result.append(SENTINEL.format(position))
        cursor = start + len(token)
    result.append(text[cursor:])
    return "".join(result), tokens


def restore(text: str, tokens: list[str]) -> str | None:
    """Restore sentinels; return None when a token was lost or duplicated."""
    used = [int(match.group(1)) for match in SENTINEL_RE.finditer(text)]
    if sorted(used) != list(range(len(tokens))):
        return None
    restored = SENTINEL_RE.sub(lambda match: tokens[int(match.group(1))], text)
    if "\u27e6PH" in restored:
        return None
    return restored


def same_placeholders(source: str, candidate: str) -> bool:
    return Counter(extract_placeholders(source)) == Counter(extract_placeholders(candidate))


def load_glossary(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise SystemExit(f"Cannot read glossary {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise SystemExit(f"Invalid JSON in glossary {path}: {error}") from error
    if not isinstance(data, dict):
        raise SystemExit(f"Glossary {path} must contain a JSON object.")
    return data


class Translator:
    """Small wrapper around the public Google Translate endpoint."""

    def __init__(self, cache_path: Path | None, batch_size: int, workers: int) -> None:
        self.cache_path = cache_path
        self.batch_size = batch_size
        self.workers = workers
        self.cache: dict[str, str] = {}
        self.failures: list[tuple[str, str, str]] = []
        if cache_path and cache_path.exists():
            try:
                loaded = json.loads(cache_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.cache = {str(key): str(value) for key, value in loaded.items()}
            except (OSError, json.JSONDecodeError):
                self.cache = {}

    @staticmethod
    def cache_key(code: str, text: str) -> str:
        return f"{code}\x00{text}"

    def save_cache(self) -> None:
        if not self.cache_path:
            return
        try:
            self.cache_path.write_text(
                json.dumps(self.cache, ensure_ascii=False, indent=0, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except OSError as error:  # pragma: no cover - best effort cache
            print(f"warning: cannot write translation cache: {error}", file=sys.stderr)

    def _request(self, texts: list[str], code: str) -> list[str] | None:
        query = BATCH_SEPARATOR.join(texts)
        params = urllib.parse.urlencode(
            {"client": "gtx", "sl": "en", "tl": code, "dt": "t", "q": query}
        )
        request = urllib.request.Request(
            f"{ENDPOINT}?{params}", headers={"User-Agent": "Mozilla/5.0 (compatible; pysplit-i18n)"}
        )
        delay = 1.0
        for attempt in range(4):
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                translated = "".join(segment[0] for segment in payload[0])
                parts = translated.split(BATCH_SEPARATOR)
                if len(parts) != len(texts):
                    return None
                return parts
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, TypeError) as error:
                if attempt == 3:
                    self.failures.append(("request", code, str(error)))
                    return None
                time.sleep(delay)
                delay *= 2
        return None

    def translate(self, texts: list[str], code: str) -> dict[str, str | None]:
        """Translate ``texts``; returns ``{source: translation-or-None}``."""
        unique = list(dict.fromkeys(texts))
        missing = [text for text in unique if self.cache_key(code, text) not in self.cache]
        chunks = [
            missing[index : index + self.batch_size]
            for index in range(0, len(missing), self.batch_size)
        ]

        def run(chunk: list[str]) -> None:
            result = self._request(chunk, code)
            if result is None:
                # Retry the chunk once as individual requests before giving up.
                for text in chunk:
                    single = self._request([text], code)
                    if single is not None:
                        self.cache[self.cache_key(code, text)] = single[0]
                return
            for source, translation in zip(chunk, result):
                self.cache[self.cache_key(code, source)] = translation

        if chunks:
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as pool:
                list(pool.map(run, chunks))

        output: dict[str, str | None] = {}
        for text in unique:
            output[text] = self.cache.get(self.cache_key(code, text))
        return output


def upstream_index(upstream_base: dict[str, object]) -> dict[str, list[str]]:
    """Map a normalised upstream English value to the upstream keys using it."""
    index: dict[str, list[str]] = {}
    for key, value in upstream_base.items():
        if isinstance(value, str):
            index.setdefault(normalise(value), []).append(key)
    return index


def value_map(
    key: str,
    source: str,
    upstream_locale: dict[str, object],
    upstream_base: dict[str, object],
    reverse: dict[str, list[str]],
) -> str | None:
    """Find a real upstream human translation for the same English value."""
    for upstream_key in reverse.get(normalise(source), []):
        translation = upstream_locale.get(upstream_key)
        upstream_english = upstream_base.get(upstream_key)
        if not isinstance(translation, str) or not isinstance(upstream_english, str):
            continue
        if not translation.strip() or normalise(translation) == normalise(upstream_english):
            continue
        if not same_placeholders(source, translation):
            continue
        return translation
    return None


def collect_targets(
    used: set[str],
    base: dict[str, object],
    locale: dict[str, object],
    skip_keys: dict[str, str],
    skip_values: dict[str, str] | None = None,
) -> list[str]:
    """Return used keys whose locale value is still the English source string."""
    skip_values = {value.casefold() for value in (skip_values or {})}
    targets: list[str] = []
    for key in sorted(used):
        source = base.get(key)
        if not isinstance(source, str) or not source.strip():
            continue
        if source.strip().casefold() in skip_values:
            continue
        if is_neutral(key, source, skip_keys):
            continue
        if locale.get(key) == source:
            targets.append(key)
    return targets


def rebuild(template: object, prefix: str, values: dict[str, object]) -> object:
    """Rebuild a catalogue using ``template`` order and flattened ``values``."""
    if not isinstance(template, dict):
        return values.get(prefix, template)
    result: dict[str, object] = {}
    for key, child in template.items():
        path = f"{prefix}.{key}" if prefix else key
        result[key] = rebuild(child, path, values)
    return result


def coverage_counts(used: set[str], base: dict[str, object], locale: dict[str, object]) -> tuple[int, int]:
    translated = sum(
        1
        for key in used
        if key in locale
        and (locale[key] != base.get(key) or is_neutral(key, base.get(key), {}))
    )
    return translated, len(used)


def translate_locale(
    locale: str,
    used: set[str],
    base: dict[str, object],
    catalogue: dict[str, object],
    upstream_base: dict[str, object],
    reverse: dict[str, list[str]],
    glossary: dict,
    translator: Translator,
    dry_run: bool,
) -> dict[str, int]:
    upstream_locale: dict[str, object] = {}
    upstream_path = UPSTREAM / f"{locale}.json"
    if upstream_path.exists():
        upstream_locale = flatten(json.loads(upstream_path.read_text(encoding="utf-8")))

    flat = flatten(catalogue)
    skip_keys = glossary.get("skipKeys", {})
    skip_values = glossary.get("skipValues", {})
    overrides = glossary.get("locales", {}).get(locale, {})
    term_context = glossary.get("termContext", {})
    stats = {
        "targets": 0,
        "value_mapped": 0,
        "overridden": 0,
        "machine": 0,
        "failed": 0,
        "unchanged": 0,
    }

    # Glossary overrides win over machine output (and over an earlier machine
    # run), so the pipeline stays idempotent when the glossary is improved.
    for key in sorted(used):
        source = base.get(key)
        if isinstance(source, str) and source in overrides and flat.get(key) != overrides[source]:
            flat[key] = overrides[source]
            stats["overridden"] += 1

    targets = collect_targets(used, base, flat, skip_keys, skip_values)
    stats["targets"] = len(targets)

    machine_keys: list[str] = []
    pending_sources: dict[str, str] = {}
    for key in targets:
        source = base[key]
        assert isinstance(source, str)
        mapped = value_map(key, source, upstream_locale, upstream_base, reverse)
        if mapped is not None:
            flat[key] = mapped
            stats["value_mapped"] += 1
            continue
        if source in overrides:
            flat[key] = overrides[source]
            stats["overridden"] += 1
            continue
        machine_keys.append(key)
        pending_sources[key] = term_context.get(source, source)

    if machine_keys:
        unique_sources = list(dict.fromkeys(pending_sources.values()))
        protected = {source: protect(source) for source in unique_sources}
        translation = translator.translate(
            [protected[source][0] for source in unique_sources], language_code(locale)
        )
        for key in machine_keys:
            source = pending_sources[key]
            masked, tokens = protected[source]
            candidate = translation.get(masked)
            restored = restore(candidate, tokens) if candidate is not None else None
            if restored is None or not restored.strip():
                stats["failed"] += 1
                continue
            flat[key] = restored.strip()
            stats["machine"] += 1

    if not dry_run and (stats["value_mapped"] or stats["overridden"] or stats["machine"]):
        merged = rebuild(catalogue if catalogue else base, "", flat)
        (CATALOGUES / f"{locale}.json").write_text(
            json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    return stats


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--locales", help="comma-separated locales (default: all non-English)")
    parser.add_argument("--glossary", type=Path, default=GLOSSARY_PATH)
    parser.add_argument(
        "--cache", type=Path, default=Path("/tmp/pysplit-i18n-cache.json")
    )
    parser.add_argument("--no-cache", action="store_true", help="ignore the HTTP cache")
    parser.add_argument("--batch-size", type=int, default=30)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true", help="report without writing files")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    glossary = load_glossary(args.glossary)
    used, unknown = collect()
    if unknown:
        print("Warning: unknown dynamic i18n key families.", file=sys.stderr)

    base = flatten(json.loads((CATALOGUES / f"{BASE_LOCALE}.json").read_text(encoding="utf-8")))
    upstream_base = flatten(json.loads((UPSTREAM / f"{BASE_LOCALE}.json").read_text(encoding="utf-8")))
    reverse = upstream_index(upstream_base)

    locales = sorted(
        path.stem
        for path in CATALOGUES.glob("*.json")
        if path.stem != BASE_LOCALE
    )
    if args.locales:
        wanted = {item.strip() for item in args.locales.split(",") if item.strip()}
        unknown_locales = wanted - set(locales)
        if unknown_locales:
            raise SystemExit(f"Unknown locale(s): {', '.join(sorted(unknown_locales))}")
        locales = [locale for locale in locales if locale in wanted]

    translator = Translator(
        None if args.no_cache else args.cache, args.batch_size, args.workers
    )
    totals = Counter()
    print(
        f"{'Locale':8} {'before':>7} {'after':>7} {'mapped':>7} {'term':>5} "
        f"{'machine':>8} {'failed':>6}"
    )
    print("-" * 61)
    for locale in locales:
        path = CATALOGUES / f"{locale}.json"
        catalogue = json.loads(path.read_text(encoding="utf-8"))
        before, total = coverage_counts(used, base, flatten(catalogue))
        stats = translate_locale(
            locale,
            used,
            base,
            catalogue,
            upstream_base,
            reverse,
            glossary,
            translator,
            args.dry_run,
        )
        if args.dry_run:
            after = before + stats["value_mapped"] + stats["overridden"] + stats["machine"]
        else:
            after, total = coverage_counts(
                used, base, flatten(json.loads(path.read_text(encoding="utf-8")))
            )
        for name in ("value_mapped", "overridden", "machine", "failed"):
            totals[name] += stats[name]
        print(
            f"{locale:8} {before * 100 / total:6.1f}% {after * 100 / total:6.1f}% "
            f"{stats['value_mapped']:7} {stats['overridden']:5} {stats['machine']:8} "
            f"{stats['failed']:6}"
        )

    translator.save_cache()
    if translator.failures:
        print(f"\n{len(translator.failures)} request(s) failed:", file=sys.stderr)
        for kind, code, error in translator.failures[:20]:
            print(f"  {kind} {code}: {error}", file=sys.stderr)
    print(
        "\nTotals: "
        f"{totals['value_mapped']} value-mapped from upstream, "
        f"{totals['overridden']} glossary overrides, "
        f"{totals['machine']} machine translated, "
        f"{totals['failed']} left English."
    )
    return 1 if totals["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
