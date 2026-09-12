"""The recorder's own tally, and the benchmark that measures the replay.

Two things nothing else in the suite watches.

The first is ``meta.kalshi``: the recorder writes its sweep tally into
every schema-2 snapshot (how many markets it saw, how many it kept, how
many events, the per-category split), and the README's venue table quotes
that tally for a named snapshot. Those figures move every day because the
venue's catalog moves, so pinning their *values* would paint the build
red on a Tuesday for no reason. What is pinned instead is that the block
exists, that it is internally consistent, and that the README's row obeys
the same arithmetic -- you cannot keep more markets than you swept.

This matters because the row got it wrong once. It claimed 123,155 swept,
77,996 of them Sports, about 48,000 kept across about 6,000 events; the
archive's own snapshots for that day say 133,136-135,289 swept, 80,092-
82,012 Sports, 54,875-56,625 kept and 7,235-7,266 events. The numbers had
been measured against a live catalog during development and never again,
which is the same failure as the "44 ladders" line the drift checker was
built to stop -- just in a place the drift checker could not see, because
they were typed rather than generated.

The second is ``scripts/bench_replay.py``. It reaches into
``replay_one(snap=...)`` and ``load_snapshot_from_blob(keep=...)``, and
nothing in CI runs it, so a signature change would rot it silently while
the README went on quoting its output. The test below runs it.
"""
from __future__ import annotations

import gzip
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

FIXTURES = Path(__file__).resolve().parent / "fixtures"
V2 = FIXTURES / "v2_20260911_0714Z.json.gz"


def _meta(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return (json.load(fh).get("meta") or {}).get("kalshi") or {}


# --------------------------------------------------------------------------
# the recorder's sweep tally
# --------------------------------------------------------------------------

def test_a_schema_2_snapshot_carries_the_recorders_sweep_tally():
    """Without this block the README's venue row has no source at all."""
    m = _meta(V2)
    for field in ("swept", "kept", "events", "by_category", "trimmed_total",
                  "trimmed_kept", "cap_hit"):
        assert field in m, field


def test_the_sweep_tally_is_internally_consistent():
    m = _meta(V2)
    assert m["swept"] == sum(m["by_category"].values()), \
        "by_category must account for every market swept"
    assert 0 < m["kept"] <= m["swept"], "cannot keep more than was swept"
    assert m["trimmed_kept"] <= m["trimmed_total"]
    assert m["events"] > 0


def test_the_sweep_did_not_silently_hit_a_page_cap():
    """A cap that is hit is a truncated catalog reported as a whole one --
    exactly the recorder-v1 defect this rebuild exists to remove."""
    m = _meta(V2)
    assert m["cap_hit"] is False
    assert m["event_cap_hit"] is False


# --------------------------------------------------------------------------
# the README row that quotes it
# --------------------------------------------------------------------------

KALSHI_ROW = re.compile(r"^\| Kalshi \|.*$", re.M)


def _kalshi_row() -> str:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    rows = KALSHI_ROW.findall(text)
    assert len(rows) == 1, f"expected one Kalshi venue row, found {len(rows)}"
    return rows[0]


def test_the_readme_kalshi_row_names_the_snapshot_it_measured():
    """A catalog figure without a date is a claim about an unspecified past.
    The row must say which snapshot it read, so it can be checked."""
    assert re.search(r"20\d\d-\d\d-\d\dT\d\d:\d\dZ", _kalshi_row()), _kalshi_row()


def test_the_readme_kalshi_row_obeys_the_arithmetic_of_a_sweep():
    """Values move with the catalog and are not pinned. The relations
    between them do not move: kept <= swept, and Sports <= swept."""
    row = _kalshi_row()
    nums = [int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", row)]
    big = [n for n in nums if n >= 1000]
    assert len(big) >= 3, f"expected swept/sports/kept in the row: {row}"
    swept = max(big)
    others = sorted(n for n in big if n != swept)
    assert all(n <= swept for n in others), row
    # The Sports slice and the kept catalog are both strictly inside the
    # sweep; if either ever equals it, the row has been mangled.
    assert others[-1] < swept, row


# --------------------------------------------------------------------------
# the benchmark behind the published timings
# --------------------------------------------------------------------------

def test_the_benchmark_still_runs_against_the_current_api(capsys):
    """bench_replay.py is the code the README's performance numbers ship
    with, and nothing else executes it. Run its per-snapshot path over the
    fixtures so a changed signature fails here rather than in a stale
    README."""
    import bench_replay

    paths = sorted(FIXTURES.glob("*.json.gz"))
    assert paths
    read = bench_replay.warm_page_cache(paths)
    assert read > 0
    bench_replay.per_snapshot(paths, reps=1)
    out = capsys.readouterr().out
    assert "load" in out and "screen" in out and "decode" in out
    # one line per recorder generation present in the fixtures
    assert "v1 " in out and "v2 " in out, out


def test_the_benchmark_exits_green_when_there_is_nothing_to_measure(tmp_path,
                                                                    capsys):
    """A state that is merely 'no archive here' must not be an error."""
    import bench_replay

    assert bench_replay.main(["--roots", str(tmp_path / "absent")]) == 0
    assert "nothing to measure" in capsys.readouterr().out


def test_the_benchmark_defaults_match_the_workflow():
    """If the analysis job's roots and the benchmark's drift apart, the
    published timing stops describing the job it is quoted about."""
    import yaml

    import bench_replay

    doc = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "analysis.yml").read_text(
            encoding="utf-8"))
    run = [s for j in doc["jobs"].values() for s in j["steps"]
           if s.get("name") == "replay the archive"][0]["run"]
    for root in bench_replay.DEFAULT_ROOTS:
        assert root in run, root
    for s in bench_replay.DEFAULT_SETTLEMENTS:
        assert s in run, s
