"""Snapshot loader shared by every analysis script.

Two snapshot schemas exist in the archive and both must keep loading:

* schema 1 (record.py v1, 2026-08-23 to the merge of v2): no ``schema``
  key; Kalshi events carry nested markets without ``event_ticker`` on the
  market; Polymarket rows carry ``liquidity`` as a JSON number in the
  earliest blobs and as a string later; zero-quote Kalshi markets were
  dropped at record time.
* schema 2 (record.py v2): top-level ``"schema": 2`` and ``"meta"``;
  Kalshi markets carry ``event_ticker``, the structured strike fields and
  a ``quoted`` flag; Polymarket rows carry ``liquidityNum``; Manifold rows
  come from search-markets sorted by liquidity.

``load_snapshot`` returns one flat list of rows per venue with every price,
size and liquidity field coerced to ``float`` (or ``None``), so downstream
code never touches the raw JSON strings. The raw document is kept on the
returned object for anything the coercion does not cover.

Polymarket eras: from 2026-08-23 to the 2026-09-01T16:44Z snapshot the
venue served rows sorted by ``liquidity`` as a string, so those slices are
not a top-1000. Rows from those snapshots are tagged ``era="string_sorted"``
and the rest ``era="numeric"``; nothing is dropped here, the analysis
decides.
"""
from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

# Last snapshot whose Polymarket slice was string-sorted (inclusive).
POLYMARKET_STRING_ERA_END = datetime(2026, 9, 1, 16, 45, tzinfo=timezone.utc)

KALSHI_EVENT_FIELDS = ("event_ticker", "series_ticker", "category",
                       "sub_title", "mutually_exclusive", "strike_period",
                       "event_title")
KALSHI_DOLLAR_FIELDS = {
    "yes_bid_dollars": "yes_bid", "yes_ask_dollars": "yes_ask",
    "no_bid_dollars": "no_bid", "no_ask_dollars": "no_ask",
    "last_price_dollars": "last_price",
}
KALSHI_FLOAT_FIELDS = {
    "volume_fp": "volume", "open_interest_fp": "open_interest",
    "yes_bid_size_fp": "yes_bid_size", "yes_ask_size_fp": "yes_ask_size",
    "floor_strike": "floor_strike", "cap_strike": "cap_strike",
}


def to_float(x) -> float | None:
    """Coerce a JSON number, numeric string or None to float (None on failure)."""
    if x is None or x == "":
        return None
    if isinstance(x, bool):
        return float(x)
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# A deadline outside this window is not one: the archive starts in 2026 and
# no listed market resolves in the fourth millennium. Bounding the epoch here
# keeps parse_time's answer the same on every platform.
_MAX_PLAUSIBLE_YEAR = 2200
_EPOCH_MIN = 0.0                                   # 1970-01-01T00:00:00Z
_EPOCH_MAX = float(datetime(_MAX_PLAUSIBLE_YEAR, 1, 1,
                            tzinfo=timezone.utc).timestamp())


def parse_time(s) -> datetime | None:
    """ISO-8601 (with Z or offset) or epoch seconds/milliseconds to aware UTC.

    Returns ``None`` rather than raising on a value no calendar can hold.
    Manifold lets its users pick any close date, and 16 of the 1,000 most
    liquid binaries on 2026-09-11 carried closeTime values from year 3022
    to 9999 (max 253402329540000 ms); ``datetime.fromtimestamp`` raises
    OSError on those on Windows and OverflowError elsewhere, which used to
    take the whole loader down on one joke market.

    The out-of-range test is an explicit bound, not the platform's. Python
    can represent year 3022 on Linux and cannot on Windows, so catching the
    exception alone made the same joke market parse differently on the two
    operating systems and the archive's meaning depend on the runner. No
    prediction market resolves after ``_MAX_PLAUSIBLE_YEAR``; a stamp beyond
    it is a typo or a joke, and either way it is not a deadline.
    """
    if s is None or s == "":
        return None
    if isinstance(s, bool):
        return None
    if isinstance(s, (int, float)):
        v = float(s)
        if abs(v) > 1e11:                    # milliseconds (Manifold)
            v /= 1000.0
        if not _EPOCH_MIN <= v <= _EPOCH_MAX:
            return None                      # not a deadline anyone will meet
        try:
            return datetime.fromtimestamp(v, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None                      # out of the representable range
    s = str(s).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    if " " in s and "T" not in s:           # Gamma closedTime "2026-08-28 22:04:52+00"
        s = s.replace(" ", "T", 1)
    if s[-3:] in ("+00", "-00"):
        s = s + ":00"
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    d = d.astimezone(timezone.utc)
    if d.year > _MAX_PLAUSIBLE_YEAR:        # same bound as the epoch branch
        return None
    return d


def parse_json_list(x) -> list | None:
    """Gamma serialises ``outcomes``/``outcomePrices`` as JSON inside a string."""
    if x is None:
        return None
    if isinstance(x, list):
        return x
    try:
        v = json.loads(x)
    except (TypeError, ValueError):
        return None
    return v if isinstance(v, list) else None


@dataclass
class Snapshot:
    path: Path
    t: datetime
    schema: int
    venues: dict[str, list[dict]]           # coerced flat rows per venue
    errors: dict[str, str] = field(default_factory=dict)
    meta: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)

    @property
    def kalshi(self) -> list[dict]:
        return self.venues.get("kalshi", [])

    @property
    def polymarket(self) -> list[dict]:
        return self.venues.get("polymarket", [])

    @property
    def predictit(self) -> list[dict]:
        return self.venues.get("predictit", [])

    @property
    def manifold(self) -> list[dict]:
        return self.venues.get("manifold", [])


def read_raw(path: str | Path) -> dict:
    p = Path(path)
    opener = gzip.open if p.suffix == ".gz" else open
    with opener(p, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def detect_schema(raw: dict) -> int:
    s = raw.get("schema")
    return int(s) if isinstance(s, int) and s > 0 else 1


def coerce_kalshi(events: list[dict], schema: int) -> list[dict]:
    """Flatten events -> one row per market with event fields attached."""
    rows: list[dict] = []
    for ev in events or []:
        evf = {k: ev.get(k) for k in KALSHI_EVENT_FIELDS if k in ev}
        if "title" in ev and "event_title" not in evf:
            evf["event_title"] = ev["title"]
        for m in ev.get("markets", []) or []:
            r = dict(m)
            r.update(evf)
            r.setdefault("event_ticker", ev.get("event_ticker"))
            for src, dst in KALSHI_DOLLAR_FIELDS.items():
                r[dst] = to_float(m.get(src))
            for src, dst in KALSHI_FLOAT_FIELDS.items():
                r[dst] = to_float(m.get(src))
            yb, ya = r["yes_bid"] or 0.0, r["yes_ask"] or 0.0
            if "quoted" not in r:
                # v1 dropped unquoted markets, so anything present was quoted.
                r["quoted"] = bool(yb > 0 or ya > 0) if schema >= 2 else True
            r["two_sided"] = bool(yb > 0 and ya > 0)
            r["close_dt"] = parse_time(m.get("close_time"))
            r["expected_expiration_dt"] = parse_time(m.get("expected_expiration_time"))
            rows.append(r)
    return rows


def coerce_polymarket(rows: list[dict], t: datetime, schema: int) -> list[dict]:
    era = "numeric"
    if schema < 2 and t <= POLYMARKET_STRING_ERA_END:
        era = "string_sorted"
    out: list[dict] = []
    for m in rows or []:
        r = dict(m)
        liq = to_float(m.get("liquidityNum"))
        if liq is None:
            liq = to_float(m.get("liquidity"))
        r["liquidity"] = liq
        r["liquidity_raw_type"] = type(m.get("liquidity")).__name__
        r["volume"] = to_float(m.get("volumeNum", m.get("volume")))
        r["bestBid"] = to_float(m.get("bestBid"))
        r["bestAsk"] = to_float(m.get("bestAsk"))
        r["outcomes"] = parse_json_list(m.get("outcomes"))
        prices = parse_json_list(m.get("outcomePrices"))
        r["outcomePrices"] = [to_float(p) for p in prices] if prices else None
        r["end_dt"] = parse_time(m.get("endDate"))
        r["expired_at_snapshot"] = bool(r["end_dt"] and r["end_dt"] < t)
        r["closed"] = bool(m.get("closed", False))
        r["era"] = era
        oc = r["outcomes"] or []
        r["yes_no"] = [str(o).lower() for o in oc] == ["yes", "no"]
        out.append(r)
    return out


def coerce_predictit(markets: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for mk in markets or []:
        for c in mk.get("contracts", []) or []:
            r = dict(c)
            r["market_id"] = mk.get("id")
            r["market_name"] = mk.get("name")
            r["contract_id"] = c.get("id")
            for k in ("bestBuyYesCost", "bestBuyNoCost", "bestSellYesCost",
                      "bestSellNoCost", "lastTradePrice"):
                r[k] = to_float(c.get(k))
            rows.append(r)
    return rows


def coerce_manifold(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for m in rows or []:
        r = dict(m)
        r["probability"] = to_float(m.get("probability"))
        r["volume"] = to_float(m.get("volume"))
        r["totalLiquidity"] = to_float(m.get("totalLiquidity"))
        r["uniqueBettorCount"] = int(to_float(m.get("uniqueBettorCount")) or 0)
        r["close_dt"] = parse_time(m.get("closeTime"))
        out.append(r)
    return out


def load_snapshot(path: str | Path) -> Snapshot:
    """Load one gzipped (or plain) snapshot of either schema into typed rows."""
    raw = read_raw(path)
    schema = detect_schema(raw)
    t = parse_time(raw.get("t"))
    if t is None:
        t = snapshot_time_from_path(path)
    venues = raw.get("venues", {}) or {}
    coerced = {
        "kalshi": coerce_kalshi(venues.get("kalshi", []), schema),
        "polymarket": coerce_polymarket(venues.get("polymarket", []), t, schema),
        "predictit": coerce_predictit(venues.get("predictit", [])),
        "manifold": coerce_manifold(venues.get("manifold", [])),
    }
    return Snapshot(path=Path(path), t=t, schema=schema, venues=coerced,
                    errors=dict(raw.get("errors", {}) or {}),
                    meta=dict(raw.get("meta", {}) or {}), raw=raw)


def snapshot_time_from_path(path: str | Path) -> datetime:
    """data/YYYYMMDD/HHMMZ.json.gz -> aware UTC datetime."""
    p = Path(path)
    day, hm = p.parent.name, p.name.split(".")[0].rstrip("Z")
    return datetime(int(day[:4]), int(day[4:6]), int(day[6:8]),
                    int(hm[:2]), int(hm[2:4]), tzinfo=timezone.utc)


def snapshot_paths(*roots: str | Path) -> list[Path]:
    """Every */*.json.gz under the given data roots, sorted by path (= by time)."""
    out: list[Path] = []
    for root in roots:
        r = Path(root)
        if r.is_dir():
            out.extend(r.glob("*/*.json.gz"))
    return sorted(set(out), key=lambda p: (p.parent.name, p.name))


def iter_snapshots(*roots: str | Path) -> Iterator[Snapshot]:
    for p in snapshot_paths(*roots):
        yield load_snapshot(p)


def kalshi_complement_identity(rows: Iterable[dict], tol: float = 1e-6) -> tuple[int, int]:
    """Count Kalshi books where no_ask != 1 - yes_bid.

    On every snapshot recorded so far the venue's NO quotes are the mirror
    image of the YES book, which makes a YES-ask + NO-ask complement screen
    tautological on Kalshi. Returns (checked, deviations); a non-zero second
    value means the venue's data model changed and the screen must be
    re-examined before any complement result is reported.
    """
    checked = deviations = 0
    for r in rows:
        yb, na = r.get("yes_bid"), r.get("no_ask")
        if yb is None or na is None or not r.get("two_sided"):
            continue
        checked += 1
        if abs((1.0 - yb) - na) > tol:
            deviations += 1
    return checked, deviations
