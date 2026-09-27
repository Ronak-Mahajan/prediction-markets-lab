"""Capture the Gamma record of every Polymarket market behind a complement violation.

The complement screen charges Polymarket's taker fee on each violation it
finds. A snapshot row that carries ``feesEnabled`` and ``feeSchedule`` is
charged its own schedule. A row without them is charged the schedule in
the file this script writes: the verbatim ``GET /markets/{id}`` record,
from the public Gamma API, of every market whose quoted outcome prices sum
below $1 in any snapshot under the given roots.
``pmlab.fees.POLYMARKET_MARKET_SCHEDULES`` is generated from that file, and
``tests/test_analysis.py`` re-derives it.

    python scripts/capture_polymarket_fees.py --roots data archive/data
    # writes docs/polymarket-market-fees-YYYY-MM-DD.json, dated in UTC
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pmlab import complement                                   # noqa: E402
from pmlab.archive import (coerce_polymarket, detect_schema,   # noqa: E402
                           parse_time, read_raw, snapshot_paths,
                           snapshot_time_from_path)

GAMMA = "https://gamma-api.polymarket.com"
UA = {"User-Agent": "prediction-markets-lab recorder/2"}
PACE = 0.1


def violating_markets(roots: list[str]) -> tuple[dict[str, dict], int]:
    """{market id: first violation seen} over every snapshot, and the count
    of snapshots read. The rule is the screen's own: a complementary pair
    of quoted prices, both inside (0, 1), summing below $1."""
    found: dict[str, dict] = {}
    paths = snapshot_paths(*[ROOT / r for r in roots])
    for p in paths:
        raw = read_raw(p)
        t = parse_time(raw.get("t")) or snapshot_time_from_path(p)
        rows = coerce_polymarket((raw.get("venues") or {}).get("polymarket", []),
                                 t, detect_schema(raw))
        for r in rows:
            pair = complement._outcome_pair(r)
            if pair is None:
                continue
            _names, (a, b) = pair
            if a + b >= 1.0 - complement.TOL:
                continue
            mid = str(r.get("id") or "")
            if mid and mid not in found:
                found[mid] = {"id": mid, "conditionId": r.get("conditionId"),
                              "first_snapshot": f"{p.parent.name}/{p.name}"}
    return found, len(paths)


def git_head(path: Path) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                             capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip() or None


def fetch(market_id: str) -> dict:
    req = urllib.request.Request(f"{GAMMA}/markets/{market_id}", headers=UA)
    for attempt in (1, 2, 3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 * attempt)
    raise RuntimeError("unreachable")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--roots", nargs="+", default=["data", "archive/data"])
    ap.add_argument("--out", default=None,
                    help="default: docs/polymarket-market-fees-<UTC date>.json")
    a = ap.parse_args(argv)

    found, n_snapshots = violating_markets(a.roots)
    ids = sorted(found, key=int)
    records = []
    for mid in ids:
        records.append(fetch(mid))
        time.sleep(PACE)
    now = datetime.now(timezone.utc)
    doc = {
        "request": f"GET {GAMMA}/markets/{{id}}",
        "read_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "selection": ("every Polymarket market whose quoted outcome prices "
                      "sum below $1 in at least one snapshot under the roots"),
        "roots": a.roots,
        "root_commits": {r: git_head(ROOT / r) for r in a.roots},
        "snapshots_read": n_snapshots,
        "violations": [found[m] for m in ids],
        "markets": records,
    }
    out = Path(a.out) if a.out else (
        ROOT / "docs" / f"polymarket-market-fees-{now:%Y-%m-%d}.json")
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"wrote {out} ({len(records)} markets from {n_snapshots} snapshots)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
