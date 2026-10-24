#!/usr/bin/env python3
"""Write the reviewed OpenAPI snapshot used by ``tests/test_openapi.py``.

Usage (from the repository root):
    backend/.venv/bin/python backend/scripts/export_openapi.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.main import create_app  # noqa: E402

SNAPSHOT = ROOT / "docs" / "openapi.json"


def main() -> int:
    spec = create_app().openapi()
    SNAPSHOT.write_text(json.dumps(spec, indent=2, sort_keys=False) + "\n")
    print(f"Wrote {SNAPSHOT.relative_to(ROOT)} ({len(spec['paths'])} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
