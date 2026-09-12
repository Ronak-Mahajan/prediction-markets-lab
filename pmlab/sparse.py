"""Which data/YYYYMMDD directories on the data branch still need indexing.

    python -m pmlab.sparse archive        # prints one "data/YYYYMMDD" per line

The settle workflow checks the data branch out as a partial clone
(blob:none) with a sparse cone, so the archive is never downloaded whole.
settle.py's index records every snapshot it has folded in; this prints
the day directories that hold blobs listed in manifest.json but not yet
in the index, and the workflow runs ``git sparse-checkout add`` on them
so exactly those blobs are fetched.
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path


def missing_days(root: str | Path) -> list[str]:
    root = Path(root)
    man_p, idx_p = root / "manifest.json", root / "settlements" / "index.json.gz"
    if not man_p.exists():
        return []
    with open(man_p, encoding="utf-8") as fh:
        blobs = json.load(fh).get("blobs", {})
    indexed: set[str] = set()
    if idx_p.exists():
        with gzip.open(idx_p, "rt", encoding="utf-8") as fh:
            indexed = set(json.load(fh).get("indexed", []))
    days = set()
    for rel in blobs:                          # data/YYYYMMDD/HHMMZ.json.gz
        parts = rel.split("/")
        if len(parts) == 3 and f"{parts[1]}/{parts[2]}" not in indexed:
            days.add(f"{parts[0]}/{parts[1]}")
    return sorted(days)


if __name__ == "__main__":
    for d in missing_days(sys.argv[1] if len(sys.argv) > 1 else "archive"):
        print(d)
