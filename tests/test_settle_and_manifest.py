"""Offline tests for settle.py bookkeeping and the archive manifest.

No network: the venue page sources are monkeypatched with canned
responses shaped like the live answers verified on 2026-09-11.
"""
from __future__ import annotations

import gzip
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import settle
from pmlab.manifest import check_manifest, update_manifest

FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 9, 12, 5, 47, tzinfo=timezone.utc)


def make_archive(tmp_path: Path) -> Path:
    """archive/data with the two v1 fixtures laid out like real snapshots."""
    root = tmp_path / "archive"
    for src, day, hm in ((FIX / "v1_20260823_0118Z.json.gz", "20260823", "0118Z"),
                         (FIX / "v1_20260910_1630Z.json.gz", "20260910", "1630Z")):
        dst = root / "data" / day / f"{hm}.json.gz"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dst)
    return root


# --------------------------------------------------------------- manifest

def test_manifest_is_incremental_and_checkable(tmp_path):
    root = make_archive(tmp_path)
    m1 = update_manifest(root)
    assert m1["snapshot_count"] == 2 and len(m1["_added"]) == 2
    assert set(m1["blobs"]) == {"data/20260823/0118Z.json.gz", "data/20260910/1630Z.json.gz"}
    assert check_manifest(root) == []
    m2 = update_manifest(root)
    assert m2["_added"] == [] and m2["manifest_sha256"] == m1["manifest_sha256"]
    # a new blob is hashed; a tampered blob is caught by --check
    new = root / "data" / "20260911" / "0714Z.json.gz"
    new.parent.mkdir()
    shutil.copy(FIX / "v2_20260911_0714Z.json.gz", new)
    m3 = update_manifest(root)
    assert m3["_added"] == ["data/20260911/0714Z.json.gz"]
    assert m3["manifest_sha256"] != m1["manifest_sha256"]
    with gzip.open(new, "wt") as fh:
        json.dump({"t": "x", "venues": {}}, fh)
    assert any(p.startswith("sha256 mismatch") for p in check_manifest(root))


def test_partial_checkout_does_not_shrink_the_manifest(tmp_path):
    """The recorder updates the manifest from a sparse checkout in which
    almost no blob is on disk. Pruning by default would rewrite the archive
    identity down to the single blob that run wrote."""
    root = make_archive(tmp_path)
    full = update_manifest(root)
    assert full["snapshot_count"] == 2

    # simulate the workflow's sparse cone: only the day just written exists
    (root / "data" / "20260823" / "0118Z.json.gz").unlink()
    (root / "data" / "20260911").mkdir()
    shutil.copy(FIX / "v2_20260911_0714Z.json.gz",
                root / "data" / "20260911" / "0714Z.json.gz")
    sparse = update_manifest(root)
    assert sparse["snapshot_count"] == 3                 # 2 kept + 1 added
    assert "data/20260823/0118Z.json.gz" in sparse["blobs"]
    assert sparse["_removed"] == []
    assert check_manifest(root) == []                    # what is on disk matches
    assert any(p.startswith("missing on disk") for p in check_manifest(root, full=True))

    # an explicit prune, which needs the whole archive on disk, does drop it
    pruned = update_manifest(root, prune=True)
    assert pruned["_removed"] == ["data/20260823/0118Z.json.gz"]
    assert pruned["snapshot_count"] == 2


# ------------------------------------------------------------------ index

def test_index_folds_each_snapshot_once(tmp_path):
    root = make_archive(tmp_path)
    index = json.loads(json.dumps(settle.EMPTY_INDEX))
    index, n = settle.update_index(index, [root / "data"])
    assert n == 2 and len(index["indexed"]) == 2
    assert "KXELONMARS-99" in index["kalshi"]
    assert "2919631" in index["polymarket"] and "559677" in index["polymarket"]
    assert index["polymarket"]["2919631"]["endDate"] == "2026-07-15T00:45:00Z"
    assert index["manifold"]["ugIszEQgAO"]["closeTime"] == 1788220740000
    assert index["predictit"]["28361"]["market_id"] == 7589
    index, n = settle.update_index(index, [root / "data"])
    assert n == 0


# ----------------------------------------------------------------- kalshi

KALSHI_PAGE = [
    {"ticker": "KXELONMARS-99", "event_ticker": "KXELONMARS-99", "result": "no",
     "settlement_value_dollars": "0.0000", "settlement_ts": "2026-09-11T06:39:09.641096Z",
     "settled_time": None, "expiration_time": "2026-09-13T00:35:00Z",
     "close_time": "2026-09-11T06:39:09Z", "status": "finalized"},
    {"ticker": "KXNEVERSEEN-1", "event_ticker": "KXNEVERSEEN-1", "result": "yes",
     "settlement_ts": "2026-09-11T06:40:53.691340Z", "status": "finalized"},
]


def fake_kalshi_pages(calls, page=None, pages_per_window=1):
    """Stand in for the venue: record each call, return one canned page."""
    page = KALSHI_PAGE if page is None else page

    def pages(min_ts, page_cap, max_ts=None):
        calls.append({"min_ts": min_ts, "max_ts": max_ts, "page_cap": page_cap})
        for i in range(min(pages_per_window, page_cap)):
            yield page, i + 1, False
        if pages_per_window > page_cap:
            yield [], page_cap, True

    return pages


def test_kalshi_keeps_recorded_tickers_dedupes_and_advances_watermark(tmp_path, monkeypatch):
    root = tmp_path / "settlements"
    index = {"kalshi": {"KXELONMARS-99": "2026-08-23T01:18:06+00:00"}}
    calls = []
    monkeypatch.setattr(settle, "kalshi_pages", fake_kalshi_pages(calls))
    r = settle.settle_kalshi(root, index, NOW, backfill=False, keep_all=False)
    assert r["mode"] == "backfill"                      # no state yet -> backfill
    assert r["head_pages"] == 0                         # no watermark yet, so no head sweep
    assert calls[0]["max_ts"] == int(NOW.timestamp())    # newest window first
    assert r["kept"] == 1
    rows = settle.read_jsonl_dir(root / "kalshi")
    assert [x["ticker"] for x in rows] == ["KXELONMARS-99"]
    assert rows[0]["result"] == "no" and rows[0]["settlement_value_dollars"] == "0.0000"
    assert "settled_time" not in rows[0]                # None values are not stored
    assert (root / "kalshi" / "20260911.jsonl").exists()
    state = json.load(open(root / "kalshi" / "state.json"))
    assert state["watermark"].startswith("2026-09-11T06:40:53")
    # a later run does the head sweep from watermark - 1 h before any backfill
    calls.clear()
    r2 = settle.settle_kalshi(root, index, NOW, backfill=False, keep_all=False)
    assert r2["head_pages"] == 1 and r2["kept"] == 0     # already recorded -> nothing new
    assert calls[0]["max_ts"] is None                    # the head sweep is unbounded above
    assert calls[0]["min_ts"] == \
        int(datetime(2026, 9, 11, 5, 40, 53, tzinfo=timezone.utc).timestamp())
    assert len(settle.read_jsonl_dir(root / "kalshi")) == 1
    # keep_all stores the unseen ticker too
    r3 = settle.settle_kalshi(root, index, NOW, backfill=False, keep_all=True)
    assert r3["kept"] == 1
    assert {x["ticker"] for x in settle.read_jsonl_dir(root / "kalshi")} == \
        {"KXELONMARS-99", "KXNEVERSEEN-1"}


def test_kalshi_backfill_walks_back_in_windows_and_resumes(tmp_path, monkeypatch):
    """The backfill is ~1,500 pages and cannot finish in one run, so it must
    record where it stopped and pick up from there, never skipping a window."""
    root = tmp_path / "settlements"
    index = {"kalshi": {}}
    calls = []
    monkeypatch.setattr(settle, "kalshi_pages", fake_kalshi_pages(calls))
    monkeypatch.setattr(settle, "KALSHI_BACKFILL_PAGE_CAP", 3)   # 3 windows per run
    r = settle.settle_kalshi(root, index, NOW, backfill=True, keep_all=False)
    assert r["backfill_windows"] == 3 and r["backfilled"] is False
    # windows walk backwards from NOW in KALSHI_BACKFILL_WINDOW steps, contiguous
    w = settle.KALSHI_BACKFILL_WINDOW
    assert [c["max_ts"] for c in calls] == [int((NOW - i * w).timestamp()) for i in range(3)]
    assert [c["min_ts"] for c in calls] == \
        [int((NOW - (i + 1) * w).timestamp()) for i in range(3)]
    cursor = settle.parse_time(r["backfill_cursor"])
    assert cursor == NOW - 3 * w

    # the next run resumes at the recorded cursor, not at NOW
    calls.clear()
    r2 = settle.settle_kalshi(root, index, NOW, backfill=True, keep_all=False)
    backfill_calls = [c for c in calls if c["max_ts"] is not None]
    assert backfill_calls[0]["max_ts"] == int(cursor.timestamp())

    # ... and it stops, and latches "backfilled", once it reaches 2026-08-23
    monkeypatch.setattr(settle, "KALSHI_BACKFILL_PAGE_CAP", 500)
    r3 = settle.settle_kalshi(root, index, NOW, backfill=True, keep_all=False)
    assert r3["backfilled"] is True
    assert settle.parse_time(r3["backfill_cursor"]) == settle.BACKFILL_FROM
    # with the backfill finished the next run is incremental only
    r4 = settle.settle_kalshi(root, index, NOW, backfill=False, keep_all=False)
    assert r4["mode"] == "incremental" and r4["backfill_pages"] == 0


def test_kalshi_capped_window_is_retried_not_skipped(tmp_path, monkeypatch):
    """If a window needs more pages than the run has left, the cursor must not
    move past it: an advanced cursor would lose those settlements for good."""
    root = tmp_path / "settlements"
    calls = []
    monkeypatch.setattr(settle, "kalshi_pages",
                        fake_kalshi_pages(calls, pages_per_window=5))
    monkeypatch.setattr(settle, "KALSHI_BACKFILL_PAGE_CAP", 2)
    r = settle.settle_kalshi(root, {"kalshi": {}}, NOW, backfill=True, keep_all=False)
    assert r["cap_hit"] is True and r["backfill_windows"] == 1
    assert settle.parse_time(r["backfill_cursor"]) == NOW      # unchanged
    assert r["backfilled"] is False


# ------------------------------------------------------------- polymarket

def test_polymarket_records_closed_and_skips_resolved(tmp_path, monkeypatch):
    root = tmp_path / "settlements"
    index = {"polymarket": {"3599945": {}, "2919631": {}, "559677": {}}}
    urls = []

    def fake_get(url, retries=3):
        urls.append(url)
        assert url.endswith("&closed=true")
        return [{"id": "3599945", "closed": True, "closedTime": "2026-08-28 22:04:52+00",
                 "umaResolutionStatus": "resolved", "outcomePrices": '["0", "1"]',
                 "outcomes": '["Yes", "No"]', "endDate": "2026-08-28T18:00:00Z",
                 "question": "q", "liquidity": "1"}]

    monkeypatch.setattr(settle, "get", fake_get)
    monkeypatch.setattr(settle, "GAMMA_PACE", 0)
    r = settle.settle_polymarket(root, index, NOW, request_cap=10)
    assert r["candidates"] == 3 and r["requests"] == 1 and r["new_records"] == 1
    assert "id=2919631" in urls[0] and "id=559677" in urls[0]
    rows = settle.read_jsonl_dir(root / "polymarket")
    assert rows[0]["umaResolutionStatus"] == "resolved" and rows[0]["closed"] is True
    r2 = settle.settle_polymarket(root, index, NOW, request_cap=10)
    assert r2["candidates"] == 2                        # the resolved id is not re-polled
    assert r2["new_records"] == 0                       # an unchanged answer is not re-stored


# --------------------------------------------------------------- manifold

def test_manifold_polls_only_past_close_and_rotates(tmp_path, monkeypatch):
    root = tmp_path / "settlements"
    past, future = 1788220740000, 4102444800000
    index = {"manifold": {"a": {"closeTime": past}, "b": {"closeTime": past},
                          "c": {"closeTime": future}}}
    answers = {"a": {"id": "a", "isResolved": True, "resolution": "YES",
                     "resolutionTime": 1787451946210, "resolutionProbability": 0.67,
                     "closeTime": past, "question": "q"},
               "b": {"id": "b", "isResolved": False, "closeTime": past}}
    monkeypatch.setattr(settle, "get", lambda url, retries=3: answers.get(url.rsplit("/", 1)[1]))
    monkeypatch.setattr(settle, "MANIFOLD_PACE", 0)
    r = settle.settle_manifold(root, index, NOW, cap=1)
    assert r["candidates"] == 2 and r["polled"] == 1 and r["capped"] is True
    r = settle.settle_manifold(root, index, NOW, cap=5)
    assert r["polled"] == 1                            # the other unresolved candidate
    rows = settle.read_jsonl_dir(root / "manifold")
    assert len(rows) == 1 and rows[0]["resolution"] == "YES"
    r = settle.settle_manifold(root, index, NOW, cap=5)
    assert r["candidates"] == 1                        # only b remains; c is in the future


# -------------------------------------------------------------- predictit

def test_predictit_disappearance_is_inferred_and_flagged(tmp_path, monkeypatch):
    root = tmp_path / "settlements"
    index = {"predictit": {
        "1": {"market_id": 10, "market_name": "M", "name": "gone-yes", "last_seen": "t0",
              "lastTradePrice": 0.97, "bestBuyYesCost": 0.98, "bestBuyNoCost": 0.03},
        "2": {"market_id": 10, "market_name": "M", "name": "gone-no", "last_seen": "t0",
              "lastTradePrice": 0.02},
        "3": {"market_id": 10, "market_name": "M", "name": "still-open", "last_seen": "t0",
              "lastTradePrice": 0.5},
    }}
    feed = {"markets": [{"id": 10, "name": "M", "contracts": [
        {"id": 3, "name": "still-open", "lastTradePrice": 0.55}]}]}
    monkeypatch.setattr(settle, "get", lambda url, retries=3: feed)
    r = settle.settle_predictit(root, index, NOW)
    assert r["new_inferred"] == 2 and r["live_contracts"] == 1
    rows = {x["contract_id"]: x for x in settle.read_jsonl_dir(root / "predictit")}
    assert rows["1"]["inferred"] is True and rows["1"]["inferred_outcome"] == "yes"
    assert rows["2"]["inferred_outcome"] == "no"
    assert index["predictit"]["3"]["lastTradePrice"] == 0.55   # live feed refreshes the index
    r2 = settle.settle_predictit(root, index, NOW)
    assert r2["new_inferred"] == 0
