"""Daily settlement capture for the four recorded venues (standard library).

The recorder only ever queries open markets, so a market that settles
simply vanishes from the archive. This job follows every market the
archive has ever quoted to its outcome and appends what it finds under
``<archive>/settlements/<venue>/YYYYMMDD.jsonl`` on the ``data`` branch.

    python settle.py --archive archive --snapshots data            # daily
    python settle.py --archive archive --snapshots data --backfill # once, from 2026-08-23

Per venue:

* Kalshi: GET /markets?status=settled&limit=1000&mve_filter=exclude
  &min_settled_ts=<watermark - 1 h>, cursor-paged (newest first; the
  server honours min_settled_ts and max_settled_ts, both verified
  2026-09-11). Rows are kept only for tickers the archive has quoted at
  least once (``--all-kalshi`` keeps everything) because the venue
  settled 73,401 markets in the 24 h to 2026-09-10T07:20Z, nearly all of
  them 15-minute crypto and per-game sports markets no snapshot ever saw.
  Deduped by (ticker, settlement_ts). The backfill to 2026-08-23 is about
  1,500 pages, far more than one run should read, so it walks backwards
  in 12-hour windows bounded by max_settled_ts and records how far it got
  in ``settlements/kalshi/state.json``; each run does the head sweep
  first, so nothing new is missed while the backfill is still catching up.
* Polymarket: every id ever recorded, in batches of 20, through Gamma
  GET /markets?id=..&id=..&closed=true. Verified 2026-09-11: the bare
  repeated-id query returns only the still-open subset and closed=true
  returns the closed complement, so absence from the closed=true answer
  means "still open". Ids whose latest record has
  umaResolutionStatus == "resolved" are not re-polled.
* Manifold: GET /v0/market/{id} for recorded ids whose closeTime has
  passed and that are not yet recorded as resolved, oldest-polled first,
  capped per run (``--manifold-cap``) because the v1 slice churned through
  tens of thousands of ids.
* PredictIt: the public feed carries open markets only, so a contract
  that leaves the feed is recorded as an inferred outcome from its last
  trade, flagged ``"inferred": true`` and excluded from headline tables.

All state (which snapshots were indexed, watermarks, poll rotation) lives
under ``settlements/`` next to the records so a fresh checkout resumes.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pmlab.archive import load_snapshot, parse_time, snapshot_paths, to_float

TIMEOUT = 30
UA = {"User-Agent": "prediction-markets-lab settle/1"}
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
GAMMA = "https://gamma-api.polymarket.com"
MANIFOLD = "https://api.manifold.markets/v0"
PREDICTIT = "https://www.predictit.org/api/marketdata/all/"

BACKFILL_FROM = datetime(2026, 8, 23, tzinfo=timezone.utc)
KALSHI_PACE = 0.15
# Measured 2026-09-11: 73,401 markets settled in the 24 h to 2026-09-10T07:20Z
# (74 pages of 1,000), almost all of them 15-minute crypto and per-game sports
# markets. The daily head sweep therefore needs ~75 pages; 200 is headroom for
# a missed run. The 2026-08-23 backfill is ~1,500 pages, so it is windowed and
# resumed across runs rather than attempted in one.
KALSHI_PAGE_CAP = 200
KALSHI_BACKFILL_PAGE_CAP = 400
KALSHI_BACKFILL_WINDOW = timedelta(hours=12)
GAMMA_BATCH = 20
GAMMA_PACE = 0.1
MANIFOLD_PACE = 0.05


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).isoformat(timespec="seconds")


def get(url: str, retries: int = 3):
    req = urllib.request.Request(url, headers=UA)
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt == retries:
                raise
        except Exception:
            if attempt == retries:
                raise
        time.sleep(2 * attempt)
    raise RuntimeError("unreachable")


# ----------------------------------------------------------------- jsonl io

def read_jsonl_dir(d: Path) -> list[dict]:
    rows: list[dict] = []
    if not d.is_dir():
        return rows
    for p in sorted(d.glob("*.jsonl")):
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, separators=(",", ":"), sort_keys=True) + "\n")


def load_json(path: Path, default):
    if not path.exists():
        return default
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".gz":
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            json.dump(obj, fh, separators=(",", ":"), sort_keys=True)
    else:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=1, sort_keys=True)
            fh.write("\n")


def day_file(root: Path, venue: str, when: datetime) -> Path:
    return root / venue / (when.strftime("%Y%m%d") + ".jsonl")


# ----------------------------------------------------------------- the index

EMPTY_INDEX = {"schema": 1, "indexed": [], "kalshi": {}, "polymarket": {},
               "manifold": {}, "predictit": {}}


def snapshot_key(p: Path) -> str:
    return f"{p.parent.name}/{p.name}"


def update_index(index: dict, roots: list[Path]) -> tuple[dict, int]:
    """Fold every not-yet-indexed snapshot into the seen-market index.

    kalshi:     ticker -> first snapshot time seen
    polymarket: id -> {"first", "last", "endDate"}
    manifold:   id -> {"first", "last", "closeTime"}
    predictit:  contract id -> last seen quotes (used to infer outcomes)
    """
    done = set(index.get("indexed", []))
    new = [p for p in snapshot_paths(*roots) if snapshot_key(p) not in done]
    for p in new:
        try:
            s = load_snapshot(p)
        except Exception as e:                  # one corrupt blob must not stop the job
            print(f"index: skipping {p}: {e!r}")
            done.add(snapshot_key(p))
            continue
        t = iso(s.t)
        for r in s.kalshi:
            index["kalshi"].setdefault(r["ticker"], t)
        for r in s.polymarket:
            e = index["polymarket"].setdefault(r["id"], {"first": t, "endDate": r.get("endDate")})
            e["last"] = t
            if r.get("endDate"):
                e["endDate"] = r["endDate"]
        for r in s.manifold:
            e = index["manifold"].setdefault(r["id"], {"first": t, "closeTime": r.get("closeTime")})
            e["last"] = t
            if r.get("closeTime") is not None:
                e["closeTime"] = r["closeTime"]
        for r in s.predictit:
            index["predictit"][str(r["contract_id"])] = {
                "market_id": r.get("market_id"), "market_name": r.get("market_name"),
                "name": r.get("name"), "last_seen": t,
                "lastTradePrice": r.get("lastTradePrice"),
                "bestBuyYesCost": r.get("bestBuyYesCost"),
                "bestBuyNoCost": r.get("bestBuyNoCost"),
            }
        done.add(snapshot_key(p))
    index["indexed"] = sorted(done)
    return index, len(new)


# ------------------------------------------------------------------- Kalshi

KALSHI_KEEP = ["ticker", "event_ticker", "result", "settlement_value_dollars",
               "settlement_ts", "settled_time", "expiration_time", "close_time",
               "status", "last_price_dollars"]


def kalshi_pages(min_ts: int, page_cap: int, max_ts: int | None = None):
    """Yield one page of settled markets at a time, newest settlement first.

    Stops when the cursor runs out or ``page_cap`` pages have been read; the
    caller is told which through the yielded ``cap_hit``.
    """
    cursor, pages = "", 0
    window = f"&max_settled_ts={max_ts}" if max_ts is not None else ""
    while True:
        url = (f"{KALSHI}/markets?status=settled&limit=1000&mve_filter=exclude"
               f"&min_settled_ts={min_ts}{window}&cursor={cursor}")
        d = get(url) or {}
        pages += 1
        yield d.get("markets", []), pages, False
        cursor = d.get("cursor") or ""
        if not cursor:
            return
        if pages >= page_cap:
            yield [], pages, True
            return
        time.sleep(KALSHI_PACE)


def settle_kalshi(root: Path, index: dict, now: datetime, backfill: bool,
                  keep_all: bool, page_cap: int | None = None) -> dict:
    """Two sweeps per run: the head since the watermark, then the backfill.

    The backfill walks backwards from the newest unswept instant in
    ``KALSHI_BACKFILL_WINDOW`` slices, bounded by ``max_settled_ts``, and
    records how far it got in ``backfill_cursor``. It has to be resumable:
    the venue settled 73,401 markets in the 24 h to 2026-09-10T07:20Z (74
    pages of 1,000), so the 2026-08-23 backfill is roughly 1,500 pages and
    cannot finish inside one run's page budget. A single unbounded sweep
    would read the newest pages, hit the cap, and leave the oldest
    settlements permanently unreachable behind an advanced watermark.

    Only tickers the archive has quoted are stored (``keep_all`` overrides),
    because the bulk of the volume is 15-minute crypto and sports markets
    that no snapshot ever saw.
    """
    state_p = root / "kalshi" / "state.json"
    state = load_json(state_p, {})
    existing = read_jsonl_dir(root / "kalshi")
    seen = {(r["ticker"], r.get("settlement_ts")) for r in existing}
    known = index["kalshi"]
    newest: datetime | None = parse_time(state.get("watermark"))
    by_day: dict[Path, list[dict]] = {}
    counts = {"scanned": 0, "kept": 0}

    def absorb(markets: list[dict]) -> None:
        nonlocal newest
        for m in markets:
            counts["scanned"] += 1
            ts = parse_time(m.get("settlement_ts") or m.get("settled_time"))
            if ts and (newest is None or ts > newest):
                newest = ts
            if not keep_all and m.get("ticker") not in known:
                continue
            key = (m.get("ticker"), m.get("settlement_ts"))
            if key in seen:
                continue
            seen.add(key)
            row = {k: m.get(k) for k in KALSHI_KEEP if m.get(k) not in (None, "")}
            row["captured"] = iso(now)
            by_day.setdefault(day_file(root, "kalshi", ts or now), []).append(row)
            counts["kept"] += 1

    do_backfill = backfill or not state.get("backfilled")
    head_budget = page_cap or KALSHI_PAGE_CAP
    back_budget = page_cap or KALSHI_BACKFILL_PAGE_CAP

    # --- head: everything settled since the watermark (skipped on run one,
    # where the backfill's first window covers the same ground).
    head_pages, head_cap_hit = 0, False
    if state.get("watermark"):
        since = parse_time(state["watermark"]) - timedelta(hours=1)
        for markets, head_pages, head_cap_hit in kalshi_pages(int(since.timestamp()),
                                                              head_budget):
            absorb(markets)

    # --- backfill: fixed-size windows walking back towards BACKFILL_FROM
    back_pages, back_cap_hit, windows = 0, False, 0
    cursor_dt = parse_time(state.get("backfill_cursor")) or now
    if do_backfill:
        while cursor_dt > BACKFILL_FROM and back_pages < back_budget:
            lower = max(BACKFILL_FROM, cursor_dt - KALSHI_BACKFILL_WINDOW)
            windows += 1
            for markets, n, hit in kalshi_pages(int(lower.timestamp()),
                                                back_budget - back_pages,
                                                max_ts=int(cursor_dt.timestamp())):
                absorb(markets)
                back_pages += 0 if hit else 1
                back_cap_hit = back_cap_hit or hit
            if back_cap_hit:
                break                       # this window is unfinished; retry it next run
            cursor_dt = lower
        state["backfill_cursor"] = iso(cursor_dt)
        if cursor_dt <= BACKFILL_FROM:
            state["backfilled"] = True

    for p, rows in by_day.items():
        append_jsonl(p, rows)
    mode = "backfill" if do_backfill else "incremental"
    state.update({"watermark": iso(newest) if newest else iso(now), "last_run": iso(now),
                  "last_mode": mode, "last_pages": head_pages + back_pages,
                  "last_cap_hit": head_cap_hit or back_cap_hit,
                  "last_scanned": counts["scanned"], "last_kept": counts["kept"],
                  "backfilled": bool(state.get("backfilled"))})
    save_json(state_p, state)
    return {"mode": mode, "head_pages": head_pages, "backfill_pages": back_pages,
            "backfill_windows": windows, "backfill_cursor": state.get("backfill_cursor"),
            "backfilled": bool(state.get("backfilled")),
            "cap_hit": head_cap_hit or back_cap_hit,
            "scanned": counts["scanned"], "kept": counts["kept"]}


# --------------------------------------------------------------- Polymarket

GAMMA_KEEP = ["id", "question", "closed", "closedTime", "umaResolutionStatus",
              "outcomePrices", "outcomes", "endDate", "conditionId"]


def settle_polymarket(root: Path, index: dict, now: datetime, request_cap: int) -> dict:
    existing = read_jsonl_dir(root / "polymarket")
    latest: dict[str, dict] = {}
    for r in existing:
        latest[r["id"]] = r
    resolved = {i for i, r in latest.items() if r.get("umaResolutionStatus") == "resolved"}
    todo = sorted(i for i in index["polymarket"] if i not in resolved)
    new_rows, requests, found = [], 0, 0
    for i in range(0, len(todo), GAMMA_BATCH):
        if requests >= request_cap:
            break
        chunk = todo[i:i + GAMMA_BATCH]
        url = f"{GAMMA}/markets?" + "&".join(f"id={c}" for c in chunk) + "&closed=true"
        try:
            rows = get(url) or []
        except Exception as e:
            print(f"polymarket: batch failed {e!r}")
            continue
        requests += 1
        for m in rows:
            found += 1
            row = {k: m.get(k) for k in GAMMA_KEEP if m.get(k) not in (None, "")}
            row["closed"] = bool(m.get("closed"))
            prev = latest.get(row["id"])
            if prev and all(prev.get(k) == row.get(k) for k in
                            ("closed", "closedTime", "umaResolutionStatus", "outcomePrices")):
                continue                        # unchanged since last record
            row["captured"] = iso(now)
            latest[row["id"]] = row
            new_rows.append(row)
        time.sleep(GAMMA_PACE)
    append_jsonl(day_file(root, "polymarket", now), new_rows)
    return {"candidates": len(todo), "requests": requests, "closed_seen": found,
            "new_records": len(new_rows), "capped": requests >= request_cap}


# ----------------------------------------------------------------- Manifold

MANIFOLD_KEEP = ["id", "question", "isResolved", "resolution", "resolutionTime",
                 "resolutionProbability", "closeTime", "probability"]


def settle_manifold(root: Path, index: dict, now: datetime, cap: int) -> dict:
    state_p = root / "manifold" / "state.json"
    state = load_json(state_p, {"polled": {}})
    existing = read_jsonl_dir(root / "manifold")
    done = {r["id"] for r in existing if r.get("isResolved") or r.get("missing")}
    now_ms = now.timestamp() * 1000
    cands = []
    for mid, e in index["manifold"].items():
        if mid in done:
            continue
        ct = to_float(e.get("closeTime"))
        if ct is None or ct > now_ms:        # not closed yet, or no usable close time
            continue
        cands.append((state["polled"].get(mid, ""), mid))
    cands.sort()                                # never polled first, then oldest poll
    new_rows, polled = [], 0
    for _, mid in cands[:cap]:
        try:
            m = get(f"{MANIFOLD}/market/{mid}")
        except Exception as e:
            print(f"manifold: {mid} failed {e!r}")
            continue
        polled += 1
        state["polled"][mid] = iso(now)
        if m is None:
            new_rows.append({"id": mid, "missing": True, "captured": iso(now)})
        elif m.get("isResolved"):
            row = {k: m.get(k) for k in MANIFOLD_KEEP if m.get(k) is not None}
            row["captured"] = iso(now)
            new_rows.append(row)
        time.sleep(MANIFOLD_PACE)
    append_jsonl(day_file(root, "manifold", now), new_rows)
    state["last_run"] = iso(now)
    save_json(state_p, state)
    return {"candidates": len(cands), "polled": polled, "resolved": len(new_rows),
            "capped": len(cands) > cap}


# ---------------------------------------------------------------- PredictIt

def settle_predictit(root: Path, index: dict, now: datetime) -> dict:
    existing = read_jsonl_dir(root / "predictit")
    done = {str(r["contract_id"]) for r in existing}
    feed = get(PREDICTIT) or {}
    live: dict[str, dict] = {}
    for mk in feed.get("markets", []):
        for c in mk.get("contracts", []):
            live[str(c.get("id"))] = {
                "market_id": mk.get("id"), "market_name": mk.get("name"),
                "name": c.get("name"), "last_seen": iso(now),
                "lastTradePrice": c.get("lastTradePrice"),
                "bestBuyYesCost": c.get("bestBuyYesCost"),
                "bestBuyNoCost": c.get("bestBuyNoCost"),
            }
    index["predictit"].update(live)             # the live feed is also a sighting
    new_rows = []
    for cid, e in index["predictit"].items():
        if cid in live or cid in done:
            continue
        ltp = e.get("lastTradePrice")
        inferred = None
        if isinstance(ltp, (int, float)):
            inferred = "yes" if ltp > 0.5 else "no" if ltp < 0.5 else None
        new_rows.append({
            "contract_id": cid, "market_id": e.get("market_id"),
            "market_name": e.get("market_name"), "name": e.get("name"),
            "last_seen": e.get("last_seen"), "disappeared_by": iso(now),
            "last_trade_price": ltp, "last_buy_yes": e.get("bestBuyYesCost"),
            "last_buy_no": e.get("bestBuyNoCost"),
            "inferred_outcome": inferred, "inferred": True,
        })
        done.add(cid)
    append_jsonl(day_file(root, "predictit", now), new_rows)
    return {"live_contracts": len(live), "known_contracts": len(index["predictit"]),
            "new_inferred": len(new_rows)}


# --------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="capture settlements for recorded markets")
    ap.add_argument("--archive", default="archive",
                    help="data-branch checkout (reads archive/data, writes archive/settlements)")
    ap.add_argument("--snapshots", action="append", default=[],
                    help="extra snapshot roots, e.g. the main-branch data/ (repeatable)")
    ap.add_argument("--backfill", action="store_true",
                    help="sweep Kalshi settlements from 2026-08-23")
    ap.add_argument("--all-kalshi", action="store_true",
                    help="keep every settled Kalshi market, not just recorded tickers")
    ap.add_argument("--manifold-cap", type=int, default=1500)
    ap.add_argument("--polymarket-request-cap", type=int, default=600)
    ap.add_argument("--kalshi-page-cap", type=int, default=None,
                    help="override the page cap (smoke tests)")
    ap.add_argument("--venues", default="kalshi,polymarket,manifold,predictit")
    a = ap.parse_args(argv)

    now = utcnow()
    archive = Path(a.archive)
    root = archive / "settlements"
    roots = [archive / "data"] + [Path(s) for s in a.snapshots]
    index_p = root / "index.json.gz"
    index = load_json(index_p, json.loads(json.dumps(EMPTY_INDEX)))
    index, n_new = update_index(index, roots)
    print(f"index: +{n_new} snapshots, {len(index['indexed'])} indexed; "
          f"kalshi {len(index['kalshi'])} tickers, polymarket {len(index['polymarket'])} ids, "
          f"manifold {len(index['manifold'])} ids, predictit {len(index['predictit'])} contracts")

    summary: dict = {"t": iso(now), "venues": {}, "errors": {}}
    jobs = {
        "kalshi": lambda: settle_kalshi(root, index, now, a.backfill, a.all_kalshi,
                                        page_cap=a.kalshi_page_cap),
        "polymarket": lambda: settle_polymarket(root, index, now, a.polymarket_request_cap),
        "manifold": lambda: settle_manifold(root, index, now, a.manifold_cap),
        "predictit": lambda: settle_predictit(root, index, now),
    }
    for name in a.venues.split(","):
        name = name.strip()
        if name not in jobs:
            continue
        t0 = time.time()
        try:
            r = jobs[name]()
            r["seconds"] = round(time.time() - t0, 1)
            summary["venues"][name] = r
            print(f"{name}: {r}")
        except Exception as e:
            summary["errors"][name] = repr(e)[:200]
            print(f"{name}: FAILED {e!r}")
    save_json(index_p, index)
    runs = load_json(root / "runs.json", [])
    runs.append(summary)
    save_json(root / "runs.json", runs[-400:])
    return 1 if summary["errors"] and not summary["venues"] else 0


if __name__ == "__main__":
    sys.exit(main())
