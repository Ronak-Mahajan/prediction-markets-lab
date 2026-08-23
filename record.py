"""Snapshot recorder for four prediction-market venues.

Fetches public market data from Kalshi, Polymarket, PredictIt, and
Manifold (no keys, no scraping, official APIs only), trims each market to
the fields the screeners need, and writes one gzipped JSON snapshot per
run. A GitHub Actions cron runs this every two hours and commits the
result, so the history accumulates with no server anywhere.

The trim matters: raw responses run to tens of MB, and a git history of
those would bloat fast. Markets with no activity are dropped, fields are
whitelisted, and a snapshot lands around a few hundred KB gzipped.

    python record.py            # writes data/YYYYMMDD/HHMMZ.json.gz
"""
from __future__ import annotations

import gzip
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
TIMEOUT = 30
UA = {"User-Agent": "prediction-markets-lab recorder"}


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


def fetch_kalshi() -> list[dict]:
    # The bare /markets feed is dominated by auto-generated provisional
    # parlay shards (tickers KXMVE*); /events with nested markets serves
    # the real catalog, and the event-level mutually_exclusive flag is
    # exactly what the bucket-sum coherence check needs.
    ekeys = ["event_ticker", "series_ticker", "category", "sub_title",
             "mutually_exclusive", "strike_period"]
    mkeys = ["ticker", "title", "yes_sub_title", "yes_bid_dollars",
             "yes_ask_dollars", "no_bid_dollars", "no_ask_dollars",
             "last_price_dollars", "volume_fp", "open_interest_fp",
             "close_time", "status"]
    out, cursor = [], ""
    for _ in range(10):                       # hard page cap
        url = ("https://api.elections.kalshi.com/trade-api/v2/events"
               "?limit=200&status=open&with_nested_markets=true"
               f"&cursor={cursor}")
        d = get(url)
        for e in d.get("events", []):
            if e.get("event_ticker", "").startswith("KXMVE"):
                continue
            markets = [pick(m, mkeys) for m in e.get("markets", [])
                       if float(m.get("yes_bid_dollars") or 0) > 0
                       or float(m.get("yes_ask_dollars") or 0) > 0]
            if markets:
                ev = pick(e, ekeys)
                ev["markets"] = markets
                out.append(ev)
        cursor = d.get("cursor") or ""
        if not cursor:
            break
    return out


def fetch_polymarket() -> list[dict]:
    keys = ["id", "question", "slug", "endDate", "liquidity", "volume",
            "bestBid", "bestAsk", "outcomePrices", "outcomes",
            "conditionId"]
    out = []
    for page in range(10):                    # the API caps pages at 100
        url = ("https://gamma-api.polymarket.com/markets?limit=100"
               "&active=true&closed=false&order=liquidity&ascending=false"
               f"&offset={page * 100}")
        rows = get(url)
        for m in rows:
            if float(m.get("liquidity") or 0) > 0:
                out.append(pick(m, keys))
        if len(rows) < 100:
            break
    return out


def fetch_predictit() -> list[dict]:
    d = get("https://www.predictit.org/api/marketdata/all/")
    out = []
    for m in d.get("markets", []):
        out.append({
            "id": m.get("id"), "name": m.get("name"),
            "contracts": [pick(c, ["id", "name", "bestBuyYesCost",
                                   "bestBuyNoCost", "bestSellYesCost",
                                   "bestSellNoCost", "lastTradePrice"])
                          for c in m.get("contracts", [])],
        })
    return out


def fetch_manifold() -> list[dict]:
    keys = ["id", "question", "probability", "outcomeType", "closeTime",
            "volume", "uniqueBettorCount", "url"]
    ms = get("https://api.manifold.markets/v0/markets?limit=1000")
    return [pick(m, keys) for m in ms
            if m.get("outcomeType") == "BINARY" and m.get("volume", 0) > 0]


def main() -> None:
    now = datetime.now(timezone.utc)
    snap: dict = {"t": now.isoformat(), "venues": {}, "errors": {}}
    for name, fn in (("kalshi", fetch_kalshi),
                     ("polymarket", fetch_polymarket),
                     ("predictit", fetch_predictit),
                     ("manifold", fetch_manifold)):
        try:
            rows = fn()
            snap["venues"][name] = rows
            print(f"{name}: {len(rows)} markets")
        except Exception as e:                # a venue outage is data too
            snap["errors"][name] = repr(e)[:200]
            print(f"{name}: FAILED {e!r}")
    out = DATA / now.strftime("%Y%m%d") / now.strftime("%H%MZ.json.gz")
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as fh:
        json.dump(snap, fh, separators=(",", ":"))
    kb = out.stat().st_size / 1024
    print(f"wrote {out} ({kb:.0f} KB)")


if __name__ == "__main__":
    main()
