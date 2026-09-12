"""Both snapshot schemas, and both Polymarket eras, load through one loader.

Fixtures (tests/fixtures/, cut from real snapshots by tests/make_fixtures.py):

* v1_20260823_0118Z.json.gz   schema 1, Polymarket string-sorted era
* v1_20260910_1630Z.json.gz   schema 1, Polymarket numeric era
* v2_synthetic.json.gz        schema 2 shape written by record.py v2

The synthetic v2 fixture is built in this file from a hand-written
document so the schema-2 contract is pinned in code, not only in a blob.
"""
from __future__ import annotations

import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pmlab.archive import (kalshi_complement_identity, load_snapshot,
                           parse_time, snapshot_paths, snapshot_time_from_path,
                           to_float)

FIX = Path(__file__).parent / "fixtures"
V1_STRING = FIX / "v1_20260823_0118Z.json.gz"
V1_NUMERIC = FIX / "v1_20260910_1630Z.json.gz"
V2_REAL = FIX / "v2_20260911_0714Z.json.gz"


def synthetic_v2() -> dict:
    return {
        "t": "2026-09-12T04:23:11.000000+00:00", "schema": 2,
        "recorder": "record.py v2",
        "venues": {
            "kalshi": [
                {"event_ticker": "KXFEDFUNDSYEAR-28JAN01", "series_ticker": "KXFEDFUNDSYEAR",
                 "category": "Economics", "sub_title": "Fed funds Jan 2028",
                 "mutually_exclusive": False,
                 "markets": [
                     {"ticker": "KXFEDFUNDSYEAR-28JAN01-T5.00", "event_ticker": "KXFEDFUNDSYEAR-28JAN01",
                      "title": "Fed funds above 5.00% in Jan 2028?", "yes_sub_title": "Above 5.00%",
                      "strike_type": "greater", "floor_strike": 5.0, "status": "active",
                      "close_time": "2028-01-31T15:00:00Z",
                      "expected_expiration_time": "2028-02-01T15:00:00Z",
                      "latest_expiration_time": "2028-02-08T15:00:00Z", "can_close_early": True,
                      "yes_bid_dollars": "0.1500", "yes_ask_dollars": "0.1600",
                      "no_bid_dollars": "0.8400", "no_ask_dollars": "0.8500",
                      "yes_bid_size_fp": "120.00", "yes_ask_size_fp": "35.00",
                      "last_price_dollars": "0.1500", "volume_fp": "1000.00",
                      "open_interest_fp": "400.00", "quoted": True},
                     {"ticker": "KXFEDFUNDSYEAR-28JAN01-T5.25", "event_ticker": "KXFEDFUNDSYEAR-28JAN01",
                      "title": "Fed funds above 5.25% in Jan 2028?", "yes_sub_title": "Above 5.25%",
                      "strike_type": "greater", "floor_strike": 5.25, "status": "active",
                      "close_time": "2028-01-31T15:00:00Z",
                      "expected_expiration_time": "2028-02-01T15:00:00Z", "can_close_early": True,
                      "yes_bid_dollars": "0.0000", "yes_ask_dollars": "0.0000",
                      "no_bid_dollars": "0.0000", "no_ask_dollars": "0.0000",
                      "last_price_dollars": "0.0000", "volume_fp": "0.00",
                      "open_interest_fp": "0.00", "quoted": False},
                 ]},
                {"event_ticker": "KXNOMETA-99", "markets": [       # event whose metadata lookup failed
                    {"ticker": "KXNOMETA-99-A", "event_ticker": "KXNOMETA-99", "title": "A?",
                     "strike_type": "custom", "status": "active",
                     "yes_bid_dollars": "0.4000", "yes_ask_dollars": "0.4200",
                     "no_bid_dollars": "0.5800", "no_ask_dollars": "0.6000", "quoted": True}]},
            ],
            "polymarket": [
                {"id": "559677", "question": "Will X win?", "slug": "will-x-win",
                 "endDate": "2028-11-07T00:00:00Z", "liquidity": "2901688.60633",
                 "liquidityNum": 2901688.60633, "volume": "43818834.26", "volumeNum": 43818834.26,
                 "bestBid": 0.001, "bestAsk": 0.002, "outcomePrices": "[\"0.0015\", \"0.9985\"]",
                 "outcomes": "[\"Yes\", \"No\"]", "conditionId": "0x66", "closed": False},
                {"id": "600001", "question": "Over/Under 21.5", "slug": "ou",
                 "endDate": "2026-10-01T00:00:00Z", "liquidityNum": 75695.07,
                 "bestBid": 0.48, "bestAsk": 0.52, "outcomePrices": "[\"0.5\", \"0.5\"]",
                 "outcomes": "[\"Over\", \"Under\"]", "conditionId": "0x67", "closed": False},
            ],
            "predictit": [
                {"id": 7589, "name": "House seats?", "status": "Open",
                 "contracts": [{"id": 28361, "name": "192 or fewer", "bestBuyYesCost": 0.23,
                                "bestBuyNoCost": 0.78, "bestSellYesCost": 0.22,
                                "bestSellNoCost": 0.77, "lastTradePrice": 0.24}]},
            ],
            "manifold": [
                {"id": "A319ydGB1B7f4PMOROL3", "question": "Will it?", "probability": 0.31,
                 "outcomeType": "BINARY", "closeTime": 1789430280000, "volume": 13734309.5,
                 "totalLiquidity": 20916, "uniqueBettorCount": 812, "isResolved": False,
                 "url": "https://manifold.markets/x/y"},
                # a real value from the 2026-09-11 sweep: year 9999, which
                # datetime.fromtimestamp cannot represent
                {"id": "zzFarFuture", "question": "Ever?", "probability": 0.5,
                 "outcomeType": "BINARY", "closeTime": 253402329540000, "volume": 12.0,
                 "totalLiquidity": 100, "uniqueBettorCount": 3, "isResolved": False},
            ],
        },
        "errors": {},
        "meta": {"kalshi": {"pages": 3, "cap_hit": False, "markets": 3, "events": 2}},
    }


@pytest.fixture(scope="module")
def v2_synthetic_path(tmp_path_factory) -> Path:
    p = tmp_path_factory.mktemp("snap") / "20260912" / "0423Z.json.gz"
    p.parent.mkdir(parents=True)
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        json.dump(synthetic_v2(), fh)
    return p


def all_fixture_paths(v2_synthetic_path) -> list[Path]:
    paths = [V1_STRING, V1_NUMERIC, v2_synthetic_path]
    if V2_REAL.exists():
        paths.append(V2_REAL)
    return paths


# ------------------------------------------------------------ every schema

def test_fixtures_exist():
    assert V1_STRING.exists() and V1_NUMERIC.exists()


def test_every_fixture_loads_with_coerced_floats(v2_synthetic_path):
    for p in all_fixture_paths(v2_synthetic_path):
        s = load_snapshot(p)
        assert s.t.tzinfo is not None and s.t.utcoffset().total_seconds() == 0
        assert s.schema in (1, 2)
        assert set(s.venues) == {"kalshi", "polymarket", "predictit", "manifold"}
        assert s.kalshi and s.polymarket and s.predictit and s.manifold, p
        for r in s.kalshi:
            for k in ("yes_bid", "yes_ask", "no_bid", "no_ask", "last_price",
                      "volume", "open_interest"):
                assert r[k] is None or isinstance(r[k], float), (p, k, r[k])
            assert isinstance(r["quoted"], bool) and isinstance(r["two_sided"], bool)
            assert r["event_ticker"], p
        for r in s.polymarket:
            assert isinstance(r["liquidity"], float), (p, r.get("id"))
            assert r["bestBid"] is None or isinstance(r["bestBid"], float)
            assert r["outcomes"] is None or isinstance(r["outcomes"], list)
            assert r["outcomePrices"] is None or all(
                x is None or isinstance(x, float) for x in r["outcomePrices"])
            assert r["era"] in ("string_sorted", "numeric")
        for r in s.predictit:
            assert r["market_id"] and r["contract_id"]
            assert r["bestBuyYesCost"] is None or isinstance(r["bestBuyYesCost"], float)
        for r in s.manifold:
            assert isinstance(r["probability"], float)
            assert r["close_dt"] is None or r["close_dt"].tzinfo is not None


def test_kalshi_complement_identity_holds_on_every_fixture(v2_synthetic_path):
    """no_ask == 1 - yes_bid on every two-sided Kalshi book: a data-quality
    invariant of the venue's data model, not a coherence result."""
    for p in all_fixture_paths(v2_synthetic_path):
        s = load_snapshot(p)
        checked, deviations = kalshi_complement_identity(s.kalshi)
        assert checked > 0, p
        assert deviations == 0, p


# --------------------------------------------------------------- schema 1

def test_v1_string_era_is_tagged_and_expired_rows_are_flagged():
    s = load_snapshot(V1_STRING)
    assert s.schema == 1
    assert s.t == datetime(2026, 8, 23, 1, 18, 6, 39604, tzinfo=timezone.utc)
    assert all(r["era"] == "string_sorted" for r in s.polymarket)
    assert all(r["liquidity_raw_type"] == "str" for r in s.polymarket)
    # the venue sorted "99.9993" above "2901688.6": every liquidity in the
    # trimmed slice starts with the digit 9 and the first row had already ended
    assert all(str(r0.get("liquidity")).startswith("9") for r0 in s.raw["venues"]["polymarket"])
    assert s.polymarket[0]["expired_at_snapshot"] is True
    assert s.polymarket[0]["end_dt"] < s.t
    # v1 dropped unquoted markets at record time, so every row is quoted
    assert all(r["quoted"] for r in s.kalshi)
    assert "floor_strike" not in s.raw["venues"]["kalshi"][0]["markets"][0]


def test_v1_numeric_era_is_a_true_top_slice():
    s = load_snapshot(V1_NUMERIC)
    assert s.schema == 1
    assert all(r["era"] == "numeric" for r in s.polymarket)
    liq = [r["liquidity"] for r in s.polymarket]
    assert liq == sorted(liq, reverse=True)
    assert liq[0] > 1_000_000
    assert not any(r["expired_at_snapshot"] for r in s.polymarket)
    yes_no = [r for r in s.polymarket if r["yes_no"]]
    assert yes_no and yes_no[0]["outcomes"] == ["Yes", "No"]


# --------------------------------------------------------------- schema 2

def test_v2_synthetic_carries_new_fields(v2_synthetic_path):
    s = load_snapshot(v2_synthetic_path)
    assert s.schema == 2
    assert s.meta["kalshi"]["cap_hit"] is False
    by_ticker = {r["ticker"]: r for r in s.kalshi}
    quoted = by_ticker["KXFEDFUNDSYEAR-28JAN01-T5.00"]
    unquoted = by_ticker["KXFEDFUNDSYEAR-28JAN01-T5.25"]
    assert quoted["quoted"] is True and quoted["two_sided"] is True
    assert unquoted["quoted"] is False and unquoted["two_sided"] is False
    assert quoted["floor_strike"] == 5.0 and quoted["strike_type"] == "greater"
    assert quoted["yes_bid_size"] == 120.0 and quoted["yes_ask_size"] == 35.0
    assert quoted["expected_expiration_dt"] == datetime(2028, 2, 1, 15, tzinfo=timezone.utc)
    assert quoted["category"] == "Economics" and quoted["mutually_exclusive"] is False
    # an event whose metadata lookup failed still yields its markets
    assert by_ticker["KXNOMETA-99-A"]["event_ticker"] == "KXNOMETA-99"
    assert by_ticker["KXNOMETA-99-A"].get("category") is None
    pm = {r["id"]: r for r in s.polymarket}
    assert pm["559677"]["liquidity"] == pytest.approx(2901688.60633)
    assert pm["559677"]["yes_no"] is True and pm["600001"]["yes_no"] is False
    assert pm["559677"]["outcomePrices"] == [0.0015, 0.9985]
    assert all(r["era"] == "numeric" for r in s.polymarket)
    assert s.manifold[0]["totalLiquidity"] == 20916.0


@pytest.mark.skipif(not V2_REAL.exists(), reason="no real v2 fixture cut yet")
def test_v2_real_fixture_has_structured_strikes_and_quoted_flag():
    s = load_snapshot(V2_REAL)
    assert s.schema == 2
    # cut from the live 2026-09-11T07:14Z run: the full open catalog was
    # swept (124 pages, no cap hit) before the Sports trim
    assert s.meta["kalshi"]["pages"] >= 1
    assert s.meta["kalshi"]["cap_hit"] is False
    assert s.meta["kalshi"]["swept"] > s.meta["kalshi"]["kept"] > 0
    assert s.meta["kalshi"]["by_category"]["Sports"] > 0
    assert s.meta["polymarket"]["kept"] > 0
    assert all(isinstance(r["quoted"], bool) for r in s.kalshi)
    assert any(r.get("strike_type") for r in s.kalshi)
    assert any(r.get("floor_strike") is not None for r in s.kalshi)
    assert any(r.get("expected_expiration_dt") is not None for r in s.kalshi)
    assert all("event_ticker" in r0 for ev in s.raw["venues"]["kalshi"] for r0 in ev["markets"])
    assert all(isinstance(r0.get("liquidityNum"), (int, float))
               for r0 in s.raw["venues"]["polymarket"])
    assert not any(r["expired_at_snapshot"] for r in s.polymarket)


# ---------------------------------------------------------------- helpers

def test_parse_time_survives_unrepresentable_epochs():
    """Manifold lets users pick any close date and some pick year 9999.

    These four values are real closeTime entries from the 1,000 most liquid
    binaries on 2026-09-11 (16 of 1,000 were out of range). Before the fix
    ``datetime.fromtimestamp`` raised OSError on Windows / OverflowError on
    Linux and one joke market took the whole loader down.
    """
    for ms in (33217163036414, 33247749540000, 49667759940000, 253402329540000):
        assert parse_time(ms) is None
    assert parse_time(-1e18) is None
    # ordinary values still parse, in both seconds and milliseconds
    assert parse_time(1789430280000) == datetime(2026, 9, 14, 23, 58, tzinfo=timezone.utc)
    assert parse_time(1789430280) == datetime(2026, 9, 14, 23, 58, tzinfo=timezone.utc)
    assert parse_time("2026-08-28 22:04:52+00") == \
        datetime(2026, 8, 28, 22, 4, 52, tzinfo=timezone.utc)
    assert parse_time("2028-01-31T15:00:00Z") == datetime(2028, 1, 31, 15, tzinfo=timezone.utc)
    assert parse_time(None) is None and parse_time("") is None and parse_time("nope") is None


def test_helpers():
    assert to_float("0.1000") == 0.1 and to_float(None) is None and to_float("") is None
    assert to_float("abc") is None and to_float(3) == 3.0
    assert snapshot_time_from_path("data/20260823/0118Z.json.gz") == \
        datetime(2026, 8, 23, 1, 18, tzinfo=timezone.utc)
    ps = snapshot_paths(FIX.parent.parent / "data")
    assert ps == sorted(ps, key=lambda p: (p.parent.name, p.name))
