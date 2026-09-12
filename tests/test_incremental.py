"""The incremental replay must be an optimisation and nothing else.

Every test here asks one question: does turning the cache on change a
number? The answer has to be no, in both directions -- a cold run after a
cached run, and a cached run after a cold one, must produce the same bytes
-- because the cache exists to make a ten-minute CI job fit in its budget,
not to produce a second, cheaper set of results.

The other half is invalidation. A cache that survives a code change would
publish a number produced by code that no longer exists, which is the one
failure this repository is built to prevent, so the fingerprint test below
is load-bearing.
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pmlab import cache as cache_mod                          # noqa: E402
from pmlab import replay as replay_mod                        # noqa: E402
from pmlab.archive import (load_snapshot, read_blob,          # noqa: E402
                           load_snapshot_from_blob, snapshot_paths)

from test_analysis import write_synthetic_snapshot            # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def build_archive(root: Path) -> None:
    write_synthetic_snapshot(root / "20260901" / "0100Z.json.gz",
                             "2026-09-01T01:00:00Z", inverted=False)
    write_synthetic_snapshot(root / "20260901" / "0400Z.json.gz",
                             "2026-09-01T04:00:00Z", inverted=True)
    write_synthetic_snapshot(root / "20260902" / "0100Z.json.gz",
                             "2026-09-02T01:00:00Z", inverted=True)


def outputs(out: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(out.iterdir())}


def replay(root: Path, out: Path, tmp: Path, cache: Path | None,
           extra: "list[str] | None" = None) -> int:
    args = ["--roots", str(root), "--out", str(out),
            "--settlements", str(tmp / "no-settlements"),
            "--events", str(tmp / "no-events.yaml"), "--no-plots", "--quiet"]
    if cache is not None:
        args += ["--cache", str(cache)]
    return replay_mod.main(args + (extra or []))


# --------------------------------------------------------------------------
# the cache changes nothing
# --------------------------------------------------------------------------

def test_a_cached_replay_produces_the_same_bytes_as_a_cold_one(tmp_path):
    root, cache = tmp_path / "data", tmp_path / "c" / "replay.json.gz"
    build_archive(root)
    out = tmp_path / "results"
    assert replay(root, out, tmp_path, None) == 0
    cold = outputs(out)
    assert replay(root, out, tmp_path, cache) == 0       # cold cache: all misses
    assert outputs(out) == cold
    assert replay(root, out, tmp_path, cache) == 0       # warm cache: all hits
    assert outputs(out) == cold


def test_a_cold_replay_after_a_cached_one_produces_the_same_bytes(tmp_path):
    root, cache = tmp_path / "data", tmp_path / "c" / "replay.json.gz"
    build_archive(root)
    out = tmp_path / "results"
    assert replay(root, out, tmp_path, cache) == 0
    assert replay(root, out, tmp_path, cache) == 0
    warm = outputs(out)
    assert replay(root, out, tmp_path, None) == 0
    assert outputs(out) == warm


def test_the_cache_is_used(tmp_path):
    """Not just harmless -- actually hit, or the test above proves nothing."""
    root, cache = tmp_path / "data", tmp_path / "c" / "replay.json.gz"
    build_archive(root)
    replay(root, tmp_path / "results", tmp_path, cache)
    c = cache_mod.ReplayCache.load(cache)
    assert len(c.entries) == 3
    assert c.get("20260901/0100Z.json.gz", "not-the-sha") is None
    key = "20260901/0400Z.json.gz"
    sha = c.entries[key]["sha256"]
    hit = c.get(key, sha)
    assert hit is not None
    assert hit["row"]["ladder_inversions_gross"] == 1


def test_a_changed_blob_is_a_cache_miss_not_a_stale_row(tmp_path):
    root, cache = tmp_path / "data", tmp_path / "c" / "replay.json.gz"
    snap = root / "20260901" / "0100Z.json.gz"
    write_synthetic_snapshot(snap, "2026-09-01T01:00:00Z", inverted=False)
    out = tmp_path / "results"
    replay(root, out, tmp_path, cache)
    before = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    write_synthetic_snapshot(snap, "2026-09-01T01:00:00Z", inverted=True)
    replay(root, out, tmp_path, cache)
    after = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert before["ladders"]["inversions_gross_total"] == 0
    assert after["ladders"]["inversions_gross_total"] == 1
    assert (after["archive"]["identity_sha256"]
            != before["archive"]["identity_sha256"])


def test_changed_code_throws_the_whole_cache_away(tmp_path):
    """A row produced by code that no longer exists must never be served."""
    root, cache = tmp_path / "data", tmp_path / "c" / "replay.json.gz"
    build_archive(root)
    replay(root, tmp_path / "results", tmp_path, cache)
    with gzip.open(cache, "rt", encoding="utf-8") as fh:
        doc = json.load(fh)
    assert doc["code_fingerprint"] == cache_mod.code_fingerprint()
    doc["code_fingerprint"] = "0" * 64
    with gzip.open(cache, "wt", encoding="utf-8") as fh:
        json.dump(doc, fh)
    c = cache_mod.ReplayCache.load(cache)
    assert c.entries == {}
    assert "code changed" in c.discarded_reason


def test_the_fingerprint_moves_when_a_module_moves(tmp_path, monkeypatch):
    before = cache_mod.code_fingerprint()
    pkg = Path(cache_mod.__file__).resolve().parent
    scratch = pkg / "_fingerprint_probe.py"
    scratch.write_text("# temporary\n", encoding="utf-8")
    try:
        assert cache_mod.code_fingerprint() != before
    finally:
        scratch.unlink()
    assert cache_mod.code_fingerprint() == before


@pytest.mark.parametrize("body", [b"not gzip at all", b""])
def test_an_unreadable_cache_is_a_miss_not_a_crash(tmp_path, body):
    p = tmp_path / "c" / "replay.json.gz"
    p.parent.mkdir(parents=True)
    p.write_bytes(body)
    c = cache_mod.ReplayCache.load(p)
    assert c.entries == {}
    assert c.discarded_reason
    root, out = tmp_path / "data", tmp_path / "results"
    build_archive(root)
    assert replay(root, out, tmp_path, p) == 0


def test_a_missing_cache_file_is_not_an_error(tmp_path):
    c = cache_mod.ReplayCache.load(tmp_path / "nope" / "replay.json.gz")
    assert c.entries == {} and c.discarded_reason == "no cache file yet"


def test_the_cache_drops_blobs_that_left_the_archive(tmp_path):
    root, cache = tmp_path / "data", tmp_path / "c" / "replay.json.gz"
    build_archive(root)
    replay(root, tmp_path / "results", tmp_path, cache)
    assert len(cache_mod.ReplayCache.load(cache).entries) == 3
    (root / "20260902" / "0100Z.json.gz").unlink()
    replay(root, tmp_path / "results", tmp_path, cache)
    entries = cache_mod.ReplayCache.load(cache).entries
    assert len(entries) == 2 and "20260902/0100Z.json.gz" not in entries


def test_a_limited_smoke_run_does_not_prune_the_rest_of_the_cache(tmp_path):
    """--limit replays the newest N snapshots. Pruning against those would
    make a one-line smoke run cost the next full run its whole cache."""
    root, cache = tmp_path / "data", tmp_path / "c" / "replay.json.gz"
    build_archive(root)
    replay(root, tmp_path / "results", tmp_path, cache)
    assert len(cache_mod.ReplayCache.load(cache).entries) == 3
    replay(root, tmp_path / "smoke", tmp_path, cache, ["--limit", "1"])
    assert len(cache_mod.ReplayCache.load(cache).entries) == 3


def test_the_cache_file_is_byte_stable(tmp_path):
    """A wall-clock gzip header would make an unchanged cache a new object
    every run, which is a new actions/cache entry every run."""
    root, cache = tmp_path / "data", tmp_path / "c" / "replay.json.gz"
    build_archive(root)
    replay(root, tmp_path / "results", tmp_path, cache)
    first = cache.read_bytes()
    replay(root, tmp_path / "results", tmp_path, cache)
    assert cache.read_bytes() == first


# --------------------------------------------------------------------------
# the archive identity is the same however it is computed
# --------------------------------------------------------------------------

def test_streamed_identity_equals_the_two_pass_one(tmp_path):
    root = tmp_path / "data"
    build_archive(root)
    paths = snapshot_paths(root)
    streamed = replay_mod.archive_identity_from_hashes(
        [(replay_mod.snapshot_key(p),
          __import__("hashlib").sha256(read_blob(p)).hexdigest())
         for p in paths])
    assert streamed == replay_mod.archive_identity(paths)


def test_streamed_identity_is_order_independent(tmp_path):
    root = tmp_path / "data"
    build_archive(root)
    paths = snapshot_paths(root)
    import hashlib
    pairs = [(replay_mod.snapshot_key(p),
              hashlib.sha256(read_blob(p)).hexdigest()) for p in paths]
    assert (replay_mod.archive_identity_from_hashes(pairs)
            == replay_mod.archive_identity_from_hashes(list(reversed(pairs))))


def test_the_identity_on_the_real_archive_fixtures_matches_both_paths():
    paths = sorted(FIXTURES.glob("*.json.gz"))
    assert paths, "the archive fixtures are missing"
    import hashlib
    pairs = [(replay_mod.snapshot_key(p),
              hashlib.sha256(read_blob(p)).hexdigest()) for p in paths]
    assert (replay_mod.archive_identity_from_hashes(pairs)
            == replay_mod.archive_identity(paths))


# --------------------------------------------------------------------------
# the filtered loader
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["v1_20260823_0118Z.json.gz",
                                  "v1_20260910_1630Z.json.gz",
                                  "v2_20260911_0714Z.json.gz"])
def test_a_filtered_load_returns_exactly_the_rows_a_full_load_would(name):
    """The saving must be rows skipped, never rows changed."""
    p = FIXTURES / name
    full = load_snapshot(p)
    keyfield = {"kalshi": "ticker", "polymarket": "id", "manifold": "id",
                "predictit": "contract_id"}
    keep = {}
    for venue, kf in keyfield.items():
        keys = [str(r[kf]) for r in full.venues[venue] if r.get(kf) is not None]
        keep[venue] = set(keys[::3])            # an arbitrary third of them
    thin = load_snapshot_from_blob(p, read_blob(p), keep=keep)
    assert thin.filtered is True and full.filtered is False
    assert thin.t == full.t and thin.schema == full.schema
    for venue, kf in keyfield.items():
        want = [r for r in full.venues[venue]
                if str(r.get(kf)) in keep[venue]]
        assert thin.venues[venue] == want, venue
        assert len(thin.venues[venue]) < len(full.venues[venue]) or not want


def test_an_empty_keep_set_keeps_nothing():
    p = FIXTURES / "v2_20260911_0714Z.json.gz"
    thin = load_snapshot_from_blob(p, read_blob(p), keep={})
    assert all(v == [] for v in thin.venues.values())
    assert thin.filtered is True


def test_screening_a_filtered_snapshot_is_refused():
    """Counting ladders over a filtered snapshot would count the filter."""
    p = FIXTURES / "v1_20260823_0118Z.json.gz"
    thin = load_snapshot_from_blob(p, read_blob(p), keep={"kalshi": set()})
    with pytest.raises(ValueError, match="filtered"):
        replay_mod.replay_one(p, snap=thin)


def test_the_join_sees_the_same_thing_through_a_filtered_snapshot():
    """What the cached path relies on: a snapshot filtered to the join's own
    key set produces the same join state as the whole snapshot."""
    from pmlab import calibration as cal
    p = FIXTURES / "v2_20260911_0714Z.json.gz"
    full = load_snapshot(p)
    tickers = [r["ticker"] for r in full.kalshi[:200]]
    settlements = cal.SettlementSet()
    for i, t in enumerate(tickers):
        settlements.by_venue.setdefault("kalshi", {})[t] = cal.Settlement(
            "kalshi", t, float(i % 2), full.t + __import__("datetime").timedelta(days=2),
            block="kalshi:2026-09-13")
    a = cal.CalibrationJoin(settlements)
    a.observe(full)
    b = cal.CalibrationJoin(settlements)
    b.observe(load_snapshot_from_blob(p, read_blob(p),
                                      keep=b.wanted_keys()))
    assert a.observations() == b.observations()
    assert a.report()["settled_markets_quoted_in_archive"] == \
        b.report()["settled_markets_quoted_in_archive"]
    assert a.report()["observations"] == b.report()["observations"] > 0
