"""Snapshot recorder for four prediction-market venues (schema 2).

Fetches public market data from Kalshi, Polymarket, PredictIt, and
Manifold (no keys, no scraping, official APIs only), trims each market to
the fields the studies need, and writes one gzipped JSON snapshot per
run. A GitHub Actions cron runs this (nominally every two hours; the
archive shows a median 3.3 h because hosted schedulers slip) and commits
the result to the ``data`` branch, so the history accumulates with no
server anywhere.

Schema 2 is additive over schema 1: the top-level keys ``t``, ``venues``
and ``errors`` are unchanged, ``schema`` and ``meta`` are new, and every
venue keeps its old shape with new fields added. Old snapshots still load
through ``pmlab.archive``.

What changed from v1 and why (each item is a defect measured in the
archive; see README "Provenance and corrections"):

* Kalshi: v1 read /events with nested markets and stopped after 10 pages
  of 200, so every snapshot held exactly 2,000 events and the per-race
  2026 winner series never appeared. v2 sweeps
  /markets?status=open&limit=1000&mve_filter=exclude to exhaustion (the
  filter removes the KXMVE parlay shards that forced v1 onto /events),
  keeps the structured strike and expiration fields, keeps zero-quote
  markets with ``quoted: false`` so ladder completeness is measurable, and
  joins event metadata through /events?tickers=... in batches.
* Polymarket: v1 trusted order=liquidity, which the venue served as a
  string for nine days (string-sorted rows, 12% already expired). v2 uses
  order=liquidityNum, coerces to float, drops rows whose endDate is
  before the snapshot time, and sorts client-side before truncating.
* Manifold: v1 used /v0/markets, documented as newest-first. v2 uses
  /v0/search-markets?sort=liquidity so the slice is the most liquid 1,000
  binaries, not the most recently created.
* PredictIt: unchanged.

    python record.py                     # writes data/YYYYMMDD/HHMMZ.json.gz
    python record.py --out archive/data  # the data-branch layout used by CI
"""
from __future__ import annotations

import argparse
import gzip
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 2
DATA = Path(__file__).resolve().parent / "data"
TIMEOUT = 30
UA = {"User-Agent": "prediction-markets-lab recorder/2"}

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
KALSHI_PAGE_CAP = 400         # safety valve: 400 x 1,000 markets; cap_hit is recorded
KALSHI_EVENT_PAGE_CAP = 300   # /events?status=open pages of 200
KALSHI_EVENT_BATCH = 100      # /events?tickers= batch (200 verified to work; 100 keeps URLs < 3 KB)
KALSHI_PACE = 0.15            # seconds between Kalshi requests (venue asks for 5-10/s)
# The open catalog held 123,155 markets on 2026-09-11, 77,996 of them Sports
# (per-game spreads, totals, quarter lines; 37k close within a week). Recording
# all of it is ~5 MB gzipped per snapshot, which is 16 GB/year at the cron's
# cadence. v2 records every non-Sports market (45,159 that day, ~2 MB) and the
# KALSHI_SPORTS_KEEP highest-open-interest Sports markets; the counts dropped
# per category go into meta so the trim is measurable in every snapshot.
KALSHI_SPORTS_KEEP = 3000
KALSHI_TRIM_CATEGORIES = ("Sports",)

GAMMA = "https://gamma-api.polymarket.com"
POLYMARKET_TARGET = 1000      # rows kept after client-side validation
POLYMARKET_PAGE_CAP = 15      # 100 rows per page; a few extra pages cover expired rows
POLYMARKET_PACE = 0.1

MANIFOLD = "https://api.manifold.markets/v0"


def get(url: str) -> dict | list:
    req = urllib.request.Request(url, headers=UA)
    for attempt in (1, 2, 3):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.load(r)
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 * attempt)
    raise RuntimeError("unreachable")


def pick(d: dict, keys: list[str]) -> dict:
    return {k: d[k] for k in keys if k in d and d[k] not in (None, "")}


def fnum(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


# --------------------------------------------------------------------- Kalshi

KALSHI_MARKET_KEYS = [
    "ticker", "event_ticker", "title", "yes_sub_title", "no_sub_title",
    "market_type", "strike_type", "floor_strike", "cap_strike",
    "open_time", "close_time", "expected_expiration_time",
    "latest_expiration_time", "expiration_time", "can_close_early", "status",
    "yes_bid_dollars", "yes_ask_dollars", "no_bid_dollars", "no_ask_dollars",
    "yes_bid_size_fp", "yes_ask_size_fp", "last_price_dollars",
    "volume_fp", "volume_24h_fp", "open_interest_fp", "liquidity_dollars",
]
KALSHI_EVENT_KEYS = ["event_ticker", "series_ticker", "category", "title",
                     "sub_title", "mutually_exclusive", "strike_period"]


def fetch_kalshi_markets(page_cap: int = KALSHI_PAGE_CAP) -> tuple[list[dict], dict]:
    """Full open catalog, one row per market, paged to exhaustion."""
    out: list[dict] = []
    cursor, pages, cap_hit = "", 0, False
    while True:
        url = (f"{KALSHI}/markets?status=open&limit=1000&mve_filter=exclude"
               f"&cursor={cursor}")
        d = get(url)
        pages += 1
        for m in d.get("markets", []):
            row = pick(m, KALSHI_MARKET_KEYS)
            row["quoted"] = bool(fnum(m.get("yes_bid_dollars")) > 0
                                 or fnum(m.get("yes_ask_dollars")) > 0)
            out.append(row)
        cursor = d.get("cursor") or ""
        if not cursor:
            break
        if pages >= page_cap:
            cap_hit = True
            break
        time.sleep(KALSHI_PACE)
    meta = {"pages": pages, "page_cap": page_cap, "cap_hit": cap_hit}
    return out, meta


def fetch_kalshi_open_events(page_cap: int = KALSHI_EVENT_PAGE_CAP) -> tuple[dict[str, dict], dict]:
    """Every open event's metadata (category, mutually_exclusive, ...) in one sweep.

    /events?status=open&limit=200 is ~70 pages for ~14k events, cheaper than
    ~140 /events?tickers= batches; the batch lookup then fills any gaps.
    """
    cache: dict[str, dict] = {}
    cursor, pages, cap_hit = "", 0, False
    while True:
        d = get(f"{KALSHI}/events?status=open&limit=200&cursor={cursor}")
        pages += 1
        for e in d.get("events", []):
            cache[e["event_ticker"]] = pick(e, KALSHI_EVENT_KEYS)
        cursor = d.get("cursor") or ""
        if not cursor:
            break
        if pages >= page_cap:
            cap_hit = True
            break
        time.sleep(KALSHI_PACE)
    return cache, {"event_pages": pages, "event_cap_hit": cap_hit}


def fetch_kalshi_events(tickers: list[str], batch: int = KALSHI_EVENT_BATCH,
                        cache: dict[str, dict] | None = None) -> tuple[dict[str, dict], dict]:
    """Event metadata by ticker, batched through /events?tickers=a,b,c."""
    cache = cache if cache is not None else {}
    missing = sorted(t for t in set(tickers) if t not in cache)
    requests = failures = 0
    for i in range(0, len(missing), batch):
        chunk = missing[i:i + batch]
        url = f"{KALSHI}/events?tickers={','.join(chunk)}"
        try:
            d = get(url)
            requests += 1
        except Exception:
            failures += 1              # the markets survive without metadata
            continue
        for e in d.get("events", []):
            cache[e["event_ticker"]] = pick(e, KALSHI_EVENT_KEYS)
        time.sleep(KALSHI_PACE)
    meta = {"ticker_requests": requests, "failed_batches": failures,
            "events_without_meta": sum(1 for t in set(tickers) if t not in cache)}
    return cache, meta


def trim_kalshi(markets: list[dict], events_meta: dict[str, dict],
                sports_keep: int = KALSHI_SPORTS_KEEP,
                trim_categories: tuple[str, ...] = KALSHI_TRIM_CATEGORIES) -> tuple[list[dict], dict]:
    """Keep every market outside the trimmed categories; within them keep the
    ``sports_keep`` highest open-interest markets. Returns (kept, meta)."""
    by_cat: dict[str, int] = {}
    keep: list[dict] = []
    pool: list[dict] = []
    for m in markets:
        cat = events_meta.get(m.get("event_ticker", ""), {}).get("category") or "(no event)"
        by_cat[cat] = by_cat.get(cat, 0) + 1
        (pool if cat in trim_categories else keep).append(m)
    pool.sort(key=lambda m: fnum(m.get("open_interest_fp")), reverse=True)
    kept_pool = pool[:sports_keep]
    cutoff = fnum(kept_pool[-1].get("open_interest_fp")) if len(pool) > sports_keep else 0.0
    meta = {"swept": len(markets), "by_category": dict(sorted(by_cat.items())),
            "trim_categories": list(trim_categories), "trimmed_total": len(pool),
            "trimmed_kept": len(kept_pool), "trimmed_oi_cutoff": cutoff,
            "kept": len(keep) + len(kept_pool)}
    return keep + kept_pool, meta


def fetch_kalshi() -> tuple[list[dict], dict]:
    """Events with nested markets, same outer shape as schema 1."""
    markets, meta = fetch_kalshi_markets()
    events_meta, emeta = fetch_kalshi_open_events()
    meta.update(emeta)
    events_meta, emeta = fetch_kalshi_events(sorted({m.get("event_ticker", "") for m in markets}),
                                             cache=events_meta)
    meta.update(emeta)
    markets, tmeta = trim_kalshi(markets, events_meta)
    meta.update(tmeta)
    by_event: dict[str, list[dict]] = {}
    for m in markets:
        by_event.setdefault(m.get("event_ticker", ""), []).append(m)
    out = []
    for et, ms in by_event.items():
        ev = dict(events_meta.get(et, {"event_ticker": et}))
        ev["markets"] = ms
        out.append(ev)
    meta["events"] = len(out)
    meta["quoted"] = sum(m["quoted"] for m in markets)
    return out, meta


# ----------------------------------------------------------------- Polymarket

POLYMARKET_KEYS = ["id", "question", "slug", "endDate", "liquidity", "liquidityNum",
                   "volume", "volumeNum", "bestBid", "bestAsk", "outcomePrices",
                   "outcomes", "conditionId", "closed", "closedTime", "negRisk",
                   "umaResolutionStatus"]


def fetch_polymarket(now: datetime) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    pages = dropped_expired = dropped_noliq = 0
    seen: set[str] = set()
    for page in range(POLYMARKET_PAGE_CAP):
        url = (f"{GAMMA}/markets?limit=100&active=true&closed=false"
               f"&order=liquidityNum&ascending=false&offset={page * 100}")
        batch = get(url)
        pages += 1
        for m in batch:
            liq = fnum(m.get("liquidityNum", m.get("liquidity")))
            if liq <= 0:
                dropped_noliq += 1
                continue
            end = _parse_iso(m.get("endDate"))
            if end is not None and end < now:
                dropped_expired += 1
                continue
            if m.get("id") in seen:
                continue
            seen.add(m.get("id"))
            r = pick(m, POLYMARKET_KEYS)
            r["liquidityNum"] = liq
            rows.append(r)
        if len(batch) < 100:
            break
        if len(rows) >= POLYMARKET_TARGET:
            break
        time.sleep(POLYMARKET_PACE)
    rows.sort(key=lambda r: r["liquidityNum"], reverse=True)   # never trust the server order
    rows = rows[:POLYMARKET_TARGET]
    meta = {"pages": pages, "kept": len(rows), "dropped_expired": dropped_expired,
            "dropped_no_liquidity": dropped_noliq,
            "min_liquidity": rows[-1]["liquidityNum"] if rows else None}
    return rows, meta


def _parse_iso(s) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


# ------------------------------------------------------------------ PredictIt

def fetch_predictit() -> tuple[list[dict], dict]:
    d = get("https://www.predictit.org/api/marketdata/all/")
    out = []
    for m in d.get("markets", []):
        out.append({
            "id": m.get("id"), "name": m.get("name"), "status": m.get("status"),
            "contracts": [pick(c, ["id", "name", "status", "bestBuyYesCost",
                                   "bestBuyNoCost", "bestSellYesCost",
                                   "bestSellNoCost", "lastTradePrice",
                                   "lastClosePrice", "dateEnd"])
                          for c in m.get("contracts", [])],
        })
    return out, {"markets": len(out),
                 "contracts": sum(len(m["contracts"]) for m in out)}


# ------------------------------------------------------------------- Manifold

MANIFOLD_KEYS = ["id", "question", "slug", "probability", "outcomeType", "closeTime",
                 "volume", "volume24Hours", "totalLiquidity", "uniqueBettorCount",
                 "isResolved", "lastBetTime", "url"]


def fetch_manifold() -> tuple[list[dict], dict]:
    ms = get(f"{MANIFOLD}/search-markets?sort=liquidity&limit=1000"
             "&filter=open&contractType=BINARY")
    rows = [pick(m, MANIFOLD_KEYS) for m in ms if m.get("outcomeType") == "BINARY"]
    return rows, {"returned": len(ms), "binary": len(rows),
                  "sort": "liquidity", "endpoint": "search-markets"}


# ----------------------------------------------------------------------- main

def snapshot(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    snap: dict = {"t": now.isoformat(), "schema": SCHEMA,
                  "recorder": "record.py v2", "venues": {}, "errors": {}, "meta": {}}
    for name, fn in (("kalshi", fetch_kalshi),
                     ("polymarket", lambda: fetch_polymarket(now)),
                     ("predictit", fetch_predictit),
                     ("manifold", fetch_manifold)):
        t0 = time.time()
        try:
            rows, meta = fn()
            snap["venues"][name] = rows
            meta["seconds"] = round(time.time() - t0, 1)
            snap["meta"][name] = meta
            print(f"{name}: {len(rows)} rows {meta}")
        except Exception as e:                # a venue outage is data too
            snap["errors"][name] = repr(e)[:200]
            print(f"{name}: FAILED {e!r}")
    return snap


def write_snapshot(snap: dict, root: Path) -> Path:
    now = datetime.fromisoformat(snap["t"])
    out = root / now.strftime("%Y%m%d") / now.strftime("%H%MZ.json.gz")
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as fh:
        json.dump(snap, fh, separators=(",", ":"))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="record one snapshot of four venues")
    ap.add_argument("--out", default=str(DATA),
                    help="data root (default: ./data; CI uses archive/data)")
    a = ap.parse_args(argv)
    snap = snapshot()
    out = write_snapshot(snap, Path(a.out))
    kb = out.stat().st_size / 1024
    print(f"wrote {out} ({kb:.0f} KB)")
    return 0 if snap["venues"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
