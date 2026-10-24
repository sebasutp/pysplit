#!/usr/bin/env python3
"""Import a legacy Prisma/SQLite Spliit database into the new schema.

Usage:
    python scripts/import_legacy_sqlite.py --source old.db --target new.db
    python scripts/import_legacy_sqlite.py --source old.db --target new.db --reset

The source is opened read-only and never modified. A non-empty target is
refused unless ``--reset`` is given. Re-running against a target imported from
the same source checksum is a no-op.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.legacy_importer import (
    ImportErrorBase,
    import_database,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="legacy SQLite file")
    parser.add_argument("--target", required=True, type=Path, help="new SQLite file")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="replace a non-empty target (the file is removed first)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="print the result as JSON instead of a summary",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = import_database(args.source, args.target, reset=args.reset)
    except ImportErrorBase as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.as_json:
        print(json.dumps(result, indent=2, default=str))
        return 0

    if result["status"] == "skipped":
        print(f"Skipped: {result['reason']}")
        print(f"  source: {result['source']}")
        print(f"  target: {result['target']}")
        print(f"  import run: {result['import_run_id']}")
        return 0

    print(f"Imported {result['source']} -> {result['target']}")
    print(f"  checksum: {result['checksum']}")
    print(f"  duration: {result['duration_ms']} ms")
    for table in sorted(result["counts"]):
        print(f"  {table}: {result['counts'][table]}")
    print(f"  seeded categories: {result['seeded_categories']}")
    print(f"  import run: {result['import_run_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
