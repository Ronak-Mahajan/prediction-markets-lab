"""Phase 3: resolution scoring and cross-venue basis.

Every score in here was worked out on paper before it was coded. The
synthetic archive in :func:`write_calibration_archive` holds four
Polymarket markets whose quotes were chosen so the Brier score is exactly
0.2975 and the log score exactly ``(ln .8 + ln .7 + ln .5 + ln .1) / 4``;
if either moves, the arithmetic changed, not the data.

The other load-bearing cases are the two refusals. A market/horizon cell
whose only quote is older than the age cap is reported unscored rather
than scored on a stale price, and a cell whose only book is one-sided is
reported unscored rather than scored on a mid that is not a price.

The third case is a refusal *not* made, and it is pinned here on purpose:
a wide two-sided book is still reported. On the 2026-09-11 archive the top
ask bin carries a -30.9 cent favourite-longshot bias over 679 forecasts
with a median spread of 86 cents, and splitting it on the spread moves the
realised frequency from 42.7% (spread above 10c, 393 forecasts) to 98.6%
(spread at or below 10c, 286 forecasts, mean ask 0.992). The tables
therefore carry a median spread per bin instead of a spread filter, and
``test_flb_bins_report_the_spread_that_explains_them`` is what keeps that
column honest.
"""
from __future__ import annotations

import gzip
import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pmlab import basis, calibration                          # noqa: E402
from pmlab import replay as replay_mod                        # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

SETTLED = "2026-02-10T00:00:00Z"


# --------------------------------------------------------------------------
# Fixture construction
# --------------------------------------------------------------------------

def poly(mid: str, bid, ask, *, question: str = "q",
         liquidity: float = 5_000.0) -> dict:
    return {"id": mid, "question": question, "slug": mid,
            "endDate": SETTLED, "liquidityNum": liquidity,
            "bestBid": bid, "bestAsk": ask,
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["0.5", "0.5"]', "conditionId": "c" + mid}


def write_snapshot(path: Path, t: str, polymarket: list[dict], *,
                   kalshi: list[dict] | None = None,
                   manifold: list[dict] | None = None,
                   predictit: list[dict] | None = None) -> None:
    doc = {"schema": 2, "t": t, "meta": {}, "errors": {},
           "venues": {"kalshi": kalshi or [], "polymarket": polymarket,
                      "predictit": predictit or [],
                      "manifold": manifold or []}}
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(doc, fh)


def write_settlements(root: Path, venue: str, rows: list[dict],
                      day: str = "20260210") -> None:
    d = root / venue
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"{day}.jsonl", "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")


def poly_settlement(mid: str, yes: bool, closed: str = SETTLED) -> dict:
    return {"id": mid, "umaResolutionStatus": "resolved", "closed": True,
            "closedTime": closed, "outcomes": '["Yes", "No"]',
            "outcomePrices": '["1", "0"]' if yes else '["0", "1"]',
            "question": "q" + mid, "captured": "2026-02-11T00:00:00Z"}


#: (id, bid at the 1 d quote, ask, settled YES?) -- the paper fixture.
#: mids are 0.80, 0.30, 0.50, 0.90 against outcomes 1, 0, 1, 0.
PAPER = [("m1", 0.70, 0.90, True),
         ("m2", 0.20, 0.40, False),
         ("m3", 0.40, 0.60, True),
         ("m4", 0.85, 0.95, False)]

PAPER_BRIER = 1.19 / 4                     # 0.2^2 + 0.3^2 + 0.5^2 + 0.9^2
PAPER_LOG = (math.log(0.8) + math.log(0.7)
             + math.log(0.5) + math.log(0.1)) / 4


def write_calibration_archive(tmp_path: Path) -> tuple[Path, Path]:
    """Three snapshots and one settlements tree; returns (data, settlements).

    Snapshot times are picked against a settlement of 2026-02-10T00:00Z so
    that the 1 d horizon (cut-off 02-09T00:00Z, floor 02-08T00:00Z) can
    only see the 02-08T12:00Z snapshot and the 1 wk horizon (cut-off
    02-03T00:00Z, floor 02-02T00:00Z) can only see the 02-02T12:00Z one.
    The 02-09T06:00Z snapshot is after every cut-off and must never be
    scored.
    """
    data = tmp_path / "data"
    # 1 wk quote: every market at 0.45/0.55, so the week-ahead mid is
    # exactly 0.50 and the week-ahead Brier is exactly the 0.25 baseline.
    week = [poly(mid, 0.45, 0.55) for mid, _, _, _ in PAPER]
    week.append(poly("m5", 0.45, 0.55))             # stale case, see below
    write_snapshot(data / "20260202" / "1200Z.json.gz",
                   "2026-02-02T12:00:00Z", week)

    day = [poly(mid, b, a) for mid, b, a, _ in PAPER]
    day.append(poly("m5", 0.45, 0.55))
    day.append(poly("m6", 0.0, 0.90))               # one-sided book
    write_snapshot(data / "20260208" / "1200Z.json.gz",
                   "2026-02-08T12:00:00Z", day)

    after = [poly(mid, 0.01, 0.99) for mid, _, _, _ in PAPER]
    after.append(poly("m5", 0.45, 0.55))
    write_snapshot(data / "20260209" / "0600Z.json.gz",
                   "2026-02-09T06:00:00Z", after)

    settle = tmp_path / "settlements"
    rows = [poly_settlement(mid, yes) for mid, _, _, yes in PAPER]
    # m5 settles five days later, so its newest quote is older than the age
    # cap at every horizon this archive can reach: two stale cells, no score.
    rows.append(poly_settlement("m5", True, "2026-02-15T00:00:00Z"))
    rows.append(poly_settlement("m6", True))
    write_settlements(settle, "polymarket", rows)
    return data, settle


def run_join(tmp_path: Path) -> dict:
    data, settle = write_calibration_archive(tmp_path)
    from pmlab.archive import iter_snapshots
    j = calibration.CalibrationJoin(calibration.load_settlements(settle))
    for s in iter_snapshots(data):
        j.observe(s)
    return j.report()


# --------------------------------------------------------------------------
# Scoring primitives, hand-computed
# --------------------------------------------------------------------------

def test_brier_score_is_the_mean_squared_error():
    ps, ys = [0.8, 0.3, 0.5, 0.9], [1.0, 0.0, 1.0, 0.0]
    assert calibration.brier_score(ps, ys) == pytest.approx(0.2975)
    assert calibration.brier_score([], []) is None


def test_log_score_is_the_mean_log_likelihood():
    ps, ys = [0.8, 0.3, 0.5, 0.9], [1.0, 0.0, 1.0, 0.0]
    lg, clipped = calibration.log_score(ps, ys)
    assert lg == pytest.approx(PAPER_LOG)
    assert lg == pytest.approx(-0.8938876922017332)
    assert clipped == 0


def test_log_score_clips_the_impossible_forecast_and_says_how_often():
    """A venue quoting 0 on a market that settled YES has made an
    infinitely bad forecast; the clip bounds it and the count reports it."""
    lg, clipped = calibration.log_score([0.0, 1.0, 0.5], [1.0, 0.0, 1.0])
    assert clipped == 2
    assert math.isfinite(lg)
    expected = (math.log(calibration.LOG_CLIP) * 2 + math.log(0.5)) / 3
    assert lg == pytest.approx(expected)


def test_skill_against_the_coin_flip():
    assert calibration.skill(0.25) == pytest.approx(0.0)
    assert calibration.skill(0.0) == pytest.approx(1.0)
    assert calibration.skill(0.2975) == pytest.approx(-0.19)
    assert calibration.skill(None) is None


@pytest.mark.parametrize("k, n, lo, hi", [
    (5, 10, 0.23659, 0.76341),
    (0, 10, 0.0, 0.27753),
    (10, 10, 0.72247, 1.0),
])
def test_wilson_interval_hand_computed(k, n, lo, hi):
    a, b = calibration.wilson_interval(k, n)
    assert a == pytest.approx(lo, abs=1e-5)
    assert b == pytest.approx(hi, abs=1e-5)


def test_wilson_interval_of_nothing_is_the_whole_line():
    assert calibration.wilson_interval(0, 0) == (0.0, 1.0)


@pytest.mark.parametrize("p, b", [(0.0, 0), (0.05, 0), (0.099, 0), (0.1, 1),
                                 (0.55, 5), (0.999, 9), (1.0, 9)])
def test_bin_index_puts_one_in_the_top_bin(p, b):
    assert calibration.bin_index(p) == b


def test_liquidity_bands_are_left_closed():
    assert calibration.liquidity_band(None) == "unknown"
    assert calibration.liquidity_band(99.0) == "<100"
    assert calibration.liquidity_band(100.0) == "100-1k"
    assert calibration.liquidity_band(1_000.0) == "1k-10k"
    assert calibration.liquidity_band(10 ** 9) == ">=100k"


# --------------------------------------------------------------------------
# The join, on the paper fixture
# --------------------------------------------------------------------------

def test_the_join_scores_the_last_quote_before_each_horizon(tmp_path):
    rep = run_join(tmp_path)
    assert rep["empty"] is False
    assert rep["settlements_read"] == 6
    # 4 paper markets x 2 horizons. m5 is stale at both, m6 is one-sided.
    assert rep["observations"] == 8
    assert rep["observations_rejected_stale"] == 2
    assert rep["observations_rejected_one_sided"] == 1
    assert rep["headline_horizon"] == "1d"


def test_brier_and_log_score_match_the_paper_fixture(tmp_path):
    d = run_join(tmp_path)["by_horizon"]["1d"]
    assert d["n"] == 4
    assert d["brier"] == pytest.approx(PAPER_BRIER)
    assert d["log_score"] == pytest.approx(PAPER_LOG)
    assert d["brier_skill_vs_5050"] == pytest.approx(-0.19)
    assert d["log_lift_vs_5050"] == pytest.approx(PAPER_LOG - math.log(0.5))
    assert d["base_rate"] == pytest.approx(0.5)
    assert d["mean_mid"] == pytest.approx(0.625)
    assert d["median_spread_cents"] == pytest.approx(20.0)


def test_the_week_ahead_quote_is_a_different_quote(tmp_path):
    """The 1 wk horizon must read the 02-02 snapshot, not the 02-08 one."""
    d = run_join(tmp_path)["by_horizon"]["1wk"]
    # The paper four only: m5 settles on 02-15, so its 1 wk cut-off is
    # 02-08T00:00Z and the 02-02 snapshot is already too old for it.
    assert d["n"] == 4
    assert d["mean_mid"] == pytest.approx(0.5)
    assert d["brier"] == pytest.approx(0.25)
    assert d["brier_skill_vs_5050"] == pytest.approx(0.0)
    assert d["log_score"] == pytest.approx(math.log(0.5))


def test_horizons_longer_than_the_archive_are_empty_and_say_why(tmp_path):
    by_h = run_join(tmp_path)["by_horizon"]
    for label in ("1mo", "2mo"):
        assert by_h[label]["n"] == 0
        assert by_h[label]["brier"] is None
        why = by_h[label]["coverage"]["why_empty"]
        assert "earliest settlement this archive can price" in why


def test_reliability_bins_are_where_the_paper_puts_them(tmp_path):
    rows = run_join(tmp_path)["reliability"]["all"]
    filled = {r["bin"]: r for r in rows if r["n"]}
    assert sorted(filled) == [3, 5, 8, 9]           # mids .30 .50 .80 .90
    assert filled[3]["frequency"] == 0.0            # m2 settled NO
    assert filled[5]["frequency"] == 1.0            # m3 settled YES
    assert filled[8]["frequency"] == 1.0            # m1 settled YES
    assert filled[9]["frequency"] == 0.0            # m4 settled NO
    assert filled[8]["mean_price"] == pytest.approx(0.80)
    lo, hi = calibration.wilson_interval(1, 1)
    assert filled[8]["wilson_lo"] == pytest.approx(lo)
    assert filled[8]["wilson_hi"] == pytest.approx(hi)


def test_one_settlement_day_gets_no_bootstrap_interval(tmp_path):
    """All four markets settle on the same day, so there is one block, and
    resampling one block with replacement is not a confidence interval."""
    rep = run_join(tmp_path)
    d = rep["by_horizon"]["1d"]
    assert d["blocks"] == 1
    assert d["brier_bootstrap_lo"] is None
    assert d["brier_bootstrap_hi"] is None
    for r in rep["reliability"]["all"]:
        assert r["bootstrap_lo"] is None
        assert r["bootstrap_blocks"] == 1


def test_favourite_longshot_is_measured_on_the_traded_prices(tmp_path):
    fl = run_join(tmp_path)["favourite_longshot"]
    ask = {r["bin"]: r for r in fl["ask"] if r["n"]}
    # asks .90 .40 .60 .95 -> bins 9, 4, 6, 9; bin 9 holds m1 (YES) and
    # m4 (NO), mean ask 0.925, realised 0.5, so the bias is -42.5 cents.
    assert sorted(ask) == [4, 6, 9]
    assert ask[9]["n"] == 2
    assert ask[9]["mean_price"] == pytest.approx(0.925)
    assert ask[9]["frequency"] == pytest.approx(0.5)
    assert ask[9]["bias_cents"] == pytest.approx(-42.5)
    bid = {r["bin"]: r for r in fl["bid"] if r["n"]}
    # bids .70 .20 .40 .85 -> bins 7, 2, 4, 8, one market each.
    assert sorted(bid) == [2, 4, 7, 8]
    assert bid[7]["bias_cents"] == pytest.approx(30.0)
    assert bid[2]["bias_cents"] == pytest.approx(-20.0)


def test_flb_bins_report_the_spread_that_explains_them(tmp_path):
    """Without this column the top ask bin looks like a market view when it
    is mostly a statement about how wide the book was."""
    fl = run_join(tmp_path)["favourite_longshot"]
    ask = {r["bin"]: r for r in fl["ask"] if r["n"]}
    # bin 9 holds m1 (0.70/0.90, 20c) and m4 (0.85/0.95, 10c): median 15c.
    assert ask[9]["median_spread_cents"] == pytest.approx(15.0)
    # bin 6 holds m3 alone, quoted 0.40/0.60.
    assert ask[6]["median_spread_cents"] == pytest.approx(20.0)
    for r in fl["bid"] + fl["ask"]:
        if not r["n"]:
            assert r["median_spread_cents"] is None


def test_the_outcome_join_is_sanity_checked_in_the_report(tmp_path):
    mm = run_join(tmp_path)["mean_mid_by_outcome"]
    assert mm["settled_yes"] == pytest.approx(0.65)   # (.80 + .50) / 2
    assert mm["settled_no"] == pytest.approx(0.60)    # (.30 + .90) / 2


def test_composition_reports_what_the_sample_is_made_of(tmp_path):
    comp = run_join(tmp_path)["composition"]
    assert comp["n"] == 4
    assert comp["by_venue"] == {"polymarket": 4}
    assert comp["settlement_blocks"] == 1
    assert comp["largest_blocks"][0]["n"] == 4


def test_a_stale_quote_is_never_scored(tmp_path):
    """m5's newest quote is 6 days before its 1 d cut-off. Scoring it would
    call a six-day-ahead price a one-day-ahead forecast."""
    rep = run_join(tmp_path)
    scored = {(o["venue"], o["key"], o["horizon"]) for o in
              [{"venue": x.venue, "key": x.key, "horizon": x.horizon}
               for x in _observations(tmp_path)]}
    assert ("polymarket", "m5", "1d") not in scored
    assert ("polymarket", "m5", "1wk") not in scored
    assert rep["observations_rejected_stale"] == 2


def test_a_one_sided_book_is_never_scored(tmp_path):
    """m6 is quoted 0.00 / 0.90. Its "mid" of 0.45 is not a price."""
    keys = {o.key for o in _observations(tmp_path)}
    assert "m6" not in keys


def _observations(tmp_path: Path):
    data, settle = write_calibration_archive(tmp_path)
    from pmlab.archive import iter_snapshots
    j = calibration.CalibrationJoin(calibration.load_settlements(settle))
    for s in iter_snapshots(data):
        j.observe(s)
    return j.observations()


def test_observation_csv_round_trips_the_scored_rows(tmp_path):
    obs = _observations(tmp_path)
    p = calibration.write_observations(obs, tmp_path / "calibration.csv")
    lines = p.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("venue,key,horizon,outcome,mid,bid,ask")
    assert len(lines) == len(obs) + 1
    body = "\n".join(lines[1:])
    assert "polymarket,m1,1d,1,0.800000,0.700000,0.900000" in body


# --------------------------------------------------------------------------
# The other venues' settlement readers
# --------------------------------------------------------------------------

def test_kalshi_settlement_reads_result_and_rejects_a_void(tmp_path):
    write_settlements(tmp_path, "kalshi", [
        {"ticker": "A", "result": "yes", "settlement_ts": SETTLED},
        {"ticker": "B", "result": "no", "settlement_ts": SETTLED},
        {"ticker": "C", "result": "", "settlement_ts": SETTLED},
        {"ticker": "D", "result": "yes"},
    ])
    s = calibration.load_settlements(tmp_path)
    assert set(s.by_venue["kalshi"]) == {"A", "B"}
    assert s.by_venue["kalshi"]["A"].outcome == 1.0
    assert s.by_venue["kalshi"]["B"].outcome == 0.0
    assert s.excluded["kalshi"]["no settlement time"] == 1


def test_manifold_mkt_and_cancel_are_not_binary_outcomes(tmp_path):
    write_settlements(tmp_path, "manifold", [
        {"id": "a", "isResolved": True, "resolution": "YES",
         "resolutionTime": 1770681600000},
        {"id": "b", "isResolved": True, "resolution": "MKT",
         "resolutionProbability": 0.4, "resolutionTime": 1770681600000},
        {"id": "c", "isResolved": True, "resolution": "CANCEL",
         "resolutionTime": 1770681600000},
        {"id": "d", "missing": True},
    ])
    s = calibration.load_settlements(tmp_path)
    assert set(s.by_venue["manifold"]) == {"a"}
    assert s.excluded["manifold"]["resolution=MKT"] == 1
    assert s.excluded["manifold"]["resolution=CANCEL"] == 1
    assert s.excluded["manifold"]["market gone from the API"] == 1


def test_predictit_outcomes_are_inferred_and_held_out_of_the_headline(tmp_path):
    write_settlements(tmp_path, "predictit", [
        {"contract_id": "1", "inferred_outcome": "yes", "inferred": True,
         "disappeared_by": SETTLED, "name": "c"},
    ])
    s = calibration.load_settlements(tmp_path)
    st = s.by_venue["predictit"]["1"]
    assert st.inferred is True
    assert "predictit" not in calibration.HEADLINE_VENUES


def test_polymarket_settlement_needs_a_resolved_binary_outcome(tmp_path):
    write_settlements(tmp_path, "polymarket", [
        poly_settlement("ok", True),
        {"id": "pending", "umaResolutionStatus": "proposed",
         "closedTime": SETTLED, "outcomes": '["Yes", "No"]',
         "outcomePrices": '["1", "0"]'},
        {"id": "split", "umaResolutionStatus": "resolved",
         "closedTime": SETTLED, "outcomes": '["Yes", "No"]',
         "outcomePrices": '["0.5", "0.5"]'},
    ])
    s = calibration.load_settlements(tmp_path)
    assert set(s.by_venue["polymarket"]) == {"ok"}
    assert s.excluded["polymarket"]["not resolved"] == 1
    assert s.excluded["polymarket"]["outcome price not 0 or 1"] == 1


def test_the_last_record_for_a_market_wins(tmp_path):
    """settle.py re-polls a market until it resolves, so a key can appear
    several times; the final record is the settlement."""
    write_settlements(tmp_path, "polymarket", [poly_settlement("m", False)],
                      day="20260210")
    write_settlements(tmp_path, "polymarket", [poly_settlement("m", True)],
                      day="20260211")
    s = calibration.load_settlements(tmp_path)
    assert s.by_venue["polymarket"]["m"].outcome == 1.0


# --------------------------------------------------------------------------
# Zero settlements: the state the repository is actually in
# --------------------------------------------------------------------------

def test_zero_settlements_is_an_empty_report_not_an_error():
    rep = calibration.empty_report()
    assert rep["empty"] is True
    assert rep["observations"] == 0
    assert rep["settlements_read"] == 0
    assert rep["note"]
    assert rep["by_horizon"] == {}


def test_a_missing_settlements_root_is_not_an_error(tmp_path):
    s = calibration.load_settlements(tmp_path / "nope")
    assert s.total() == 0
    assert s.files_read == 0


def test_replay_runs_end_to_end_with_zero_settlements(tmp_path):
    data = tmp_path / "data"
    write_snapshot(data / "20260208" / "1200Z.json.gz",
                   "2026-02-08T12:00:00Z", [poly("m1", 0.45, 0.55)])
    out = tmp_path / "results"
    rc = replay_mod.main(["--roots", str(data), "--out", str(out),
                          "--settlements", str(tmp_path / "none"),
                          "--events", str(tmp_path / "none.yaml"),
                          "--no-plots", "--quiet"])
    assert rc == 0
    with open(out / "summary.json", encoding="utf-8") as fh:
        s = json.load(fh)
    assert s["calibration"]["empty"] is True
    assert s["calibration"]["note"]
    assert s["basis"]["empty"] is True
    assert not (out / "calibration.csv").exists()
    body = (out / "README.md").read_text(encoding="utf-8")
    assert "## Calibration" in body
    assert "## Cross-venue basis" in body
    assert calibration.EMPTY_NOTE in body


def test_replay_writes_the_calibration_tables_when_settlements_exist(tmp_path):
    data, settle = write_calibration_archive(tmp_path)
    out = tmp_path / "results"
    rc = replay_mod.main(["--roots", str(data), "--out", str(out),
                          "--settlements", str(settle),
                          "--events", str(ROOT / "events.yaml"),
                          "--no-plots", "--quiet"])
    assert rc == 0
    with open(out / "summary.json", encoding="utf-8") as fh:
        s = json.load(fh)
    c = s["calibration"]
    assert c["empty"] is False
    assert c["by_horizon"]["1d"]["brier"] == pytest.approx(PAPER_BRIER)
    assert (out / "calibration.csv").exists()
    body = (out / "README.md").read_text(encoding="utf-8")
    assert "### By horizon" in body
    assert "0.2975" in body
    assert "### Favourite-longshot bias" in body


def test_calibration_output_is_byte_stable_across_runs(tmp_path):
    """CI commits results/; an unchanged archive must produce no diff, and
    the block bootstrap is the part most likely to break that."""
    data, settle = write_calibration_archive(tmp_path)
    outs = []
    for name in ("a", "b"):
        out = tmp_path / name
        replay_mod.main(["--roots", str(data), "--out", str(out),
                         "--settlements", str(settle),
                         "--events", str(ROOT / "events.yaml"),
                         "--no-plots", "--quiet"])
        with open(out / "summary.json", encoding="utf-8") as fh:
            d = json.load(fh)
        d.pop("generated", None)
        outs.append((json.dumps(d, sort_keys=True),
                     (out / "calibration.csv").read_bytes()))
    assert outs[0][0] == outs[1][0]
    assert outs[0][1] == outs[1][1]


def test_the_reliability_figures_render_both_full_and_empty(tmp_path):
    """The figure set must be the same shape before and after the first
    settlement, or results/README.md links a file that is not there."""
    pytest.importorskip("matplotlib")
    from pmlab import replay as R
    empty = tmp_path / "empty"
    empty.mkdir()
    written = R.write_calibration_plots(calibration.empty_report(), empty)
    assert {p.name for p in written} == {"reliability.svg",
                                         "favourite_longshot.svg"}
    assert all(p.stat().st_size > 0 for p in written)

    full = tmp_path / "full"
    full.mkdir()
    written = R.write_calibration_plots(run_join(tmp_path), full)
    assert all(p.stat().st_size > 0 for p in written)
    for p in written:
        assert "nan" not in p.read_text(encoding="utf-8").lower()


# --------------------------------------------------------------------------
# Basis: the curated map
# --------------------------------------------------------------------------

def test_the_shipped_events_file_parses_and_is_entirely_unverified():
    pf = basis.load_pairs(ROOT / "events.yaml")
    assert pf.exists and pf.parsed
    assert pf.rejected == []
    assert len(pf.pairs) >= 5
    assert pf.verified == [], "a skeleton pair must never claim verification"
    for p in pf.pairs:
        assert p.note, f"{p.id} must say what a person has to check"
        assert len(p.legs) == 2


def test_an_unquoted_yaml_side_is_a_boolean_and_is_put_back(tmp_path):
    """YAML 1.1 reads a bare `yes` as True. A curator will type it."""
    p = tmp_path / "e.yaml"
    p.write_text(
        "pairs:\n"
        "  - id: x\n    verified: false\n    legs:\n"
        "      - {venue: kalshi, key: A, side: yes}\n"
        "      - {venue: polymarket, key: '1', side: no}\n",
        encoding="utf-8")
    pf = basis.load_pairs(p)
    assert pf.rejected == []
    assert [leg.side for leg in pf.pairs[0].legs] == ["yes", "no"]


def test_a_manifold_leg_is_refused_because_it_is_play_money(tmp_path):
    p = tmp_path / "e.yaml"
    p.write_text(
        "pairs:\n"
        "  - id: x\n    legs:\n"
        "      - {venue: kalshi, key: A}\n"
        "      - {venue: manifold, key: B}\n", encoding="utf-8")
    pf = basis.load_pairs(p)
    assert pf.pairs == []
    assert "play money" in pf.rejected[0]["reason"]


def test_verified_without_a_date_is_a_claim_not_a_check(tmp_path):
    p = tmp_path / "e.yaml"
    p.write_text(
        "pairs:\n"
        "  - id: x\n    verified: true\n    legs:\n"
        "      - {venue: kalshi, key: A}\n"
        "      - {venue: polymarket, key: '1'}\n", encoding="utf-8")
    pf = basis.load_pairs(p)
    assert pf.pairs == []
    assert "checked_on" in pf.rejected[0]["reason"]


def test_both_legs_on_one_venue_is_not_a_cross_venue_pair(tmp_path):
    p = tmp_path / "e.yaml"
    p.write_text(
        "pairs:\n"
        "  - id: x\n    legs:\n"
        "      - {venue: kalshi, key: A}\n"
        "      - {venue: kalshi, key: B}\n", encoding="utf-8")
    pf = basis.load_pairs(p)
    assert pf.pairs == []
    assert "same venue" in pf.rejected[0]["reason"]


def test_a_missing_events_file_is_a_reported_state(tmp_path):
    pf = basis.load_pairs(tmp_path / "nope.yaml")
    assert pf.exists is False
    assert "does not exist" in pf.reason
    rep = basis.BasisJoin(pf).report()
    assert rep["empty"] is True
    assert rep["note"]


def test_pyyaml_missing_is_said_out_loud_not_swallowed(tmp_path, monkeypatch):
    """Silently reporting "no pairs" for a file full of them would make the
    stdlib-only replay path disagree with the CI one without saying so."""
    p = tmp_path / "e.yaml"
    p.write_text("pairs: []\n", encoding="utf-8")
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) \
        else __builtins__.__import__

    def blocked(name, *a, **k):
        if name == "yaml":
            raise ImportError("no yaml here")
        return real_import(name, *a, **k)

    monkeypatch.setattr("builtins.__import__", blocked)
    pf = basis.load_pairs(p)
    assert pf.exists is True and pf.parsed is False
    assert "PyYAML is not installed" in pf.reason


# --------------------------------------------------------------------------
# Basis: the arithmetic
# --------------------------------------------------------------------------

def test_pair_edges_are_hand_computed():
    """Kalshi 0.55/0.60 against Polymarket 0.65/0.70.

    A->B: buy Kalshi YES at 0.60 and Polymarket NO at 1 - 0.65 = 0.35;
    the pair pays $1, so the gross edge is 0.05. Kalshi charges
    ceil(0.07 * 0.60 * 0.40) = ceil(0.0168) = 0.02 and Polymarket charges
    nothing, so the net edge is 0.03.
    """
    a, b = (0.55, 0.60), (0.65, 0.70)
    e = basis.pair_edges(a, b, basis.Leg("kalshi", "A"),
                         basis.Leg("polymarket", "1"))
    assert e["gross_ab"] == pytest.approx(0.05)
    assert e["net_ab"] == pytest.approx(0.03)
    assert e["gross_ba"] == pytest.approx(-0.15)
    assert e["net_ba"] == pytest.approx(-0.17)
    assert e["best_direction"] == "a->b"
    assert e["best_net"] == pytest.approx(0.03)


def test_a_no_leg_is_the_complement_of_the_recorded_book():
    row = {"yes_bid": 0.30, "yes_ask": 0.40, "two_sided": True,
           "open_interest": 10.0, "category": "Economics"}
    assert basis.leg_quote("kalshi", row, "yes") == (0.30, 0.40)
    assert basis.leg_quote("kalshi", row, "no") == pytest.approx((0.60, 0.70))


def test_predictit_leg_fee_is_an_upper_bound():
    """10% of the profit plus 5% of what comes back off the site."""
    f = basis.leg_fee("predictit", 0.60)
    proceeds = 1.0 - 0.10 * 0.40
    proceeds -= 0.05 * proceeds
    assert f == pytest.approx(1.0 - proceeds)
    assert basis.leg_fee("polymarket", 0.60) == 0.0
    assert basis.leg_fee("kalshi", 0.60) == pytest.approx(0.02)


def test_ar1_half_life_of_a_known_decay():
    """b[i] = 10 * 0.5^i sampled every 3 h has phi exactly 0.5 and a
    half-life of exactly one step, so exactly 3 hours."""
    vals = [10.0 * 0.5 ** i for i in range(26)]
    gaps = [3.0] * 25
    hl = basis.ar1_half_life(vals, gaps)
    assert hl["phi"] == pytest.approx(0.5)
    assert hl["median_step_hours"] == pytest.approx(3.0)
    assert hl["half_life_hours"] == pytest.approx(3.0)
    assert hl["reason"] == ""


def test_a_series_that_does_not_revert_reports_no_half_life():
    vals = [1.0] * 30
    hl = basis.ar1_half_life(vals, [3.0] * 29)
    assert hl["half_life_hours"] is None
    assert "not mean-reverting" in hl["reason"]


def test_too_few_steps_reports_no_half_life():
    hl = basis.ar1_half_life([1.0, 0.5, 0.25], [3.0, 3.0])
    assert hl["half_life_hours"] is None
    assert "fewer than" in hl["reason"]


def test_a_verified_pair_is_priced_across_the_archive(tmp_path):
    """One verified pair, a constant 5-cent mid basis, 24 snapshots."""
    data = tmp_path / "data"
    for i in range(24):
        t = f"2026-02-{2 + i // 8:02d}T{(i % 8) * 3:02d}:00:00Z"
        write_snapshot(
            data / f"202602{2 + i // 8:02d}" / f"{(i % 8) * 3:02d}00Z.json.gz",
            t, [poly("1", 0.55, 0.65)],
            kalshi=[{"event_ticker": "E", "series_ticker": "S",
                     "category": "Economics", "markets": [{
                         "ticker": "A", "title": "t", "yes_sub_title": "s",
                         "yes_bid_dollars": "0.6500",
                         "yes_ask_dollars": "0.7500",
                         "no_bid_dollars": "0.2500",
                         "no_ask_dollars": "0.3500",
                         "open_interest_fp": "10", "volume_fp": "1",
                         "close_time": "2027-01-01T00:00:00Z"}]}])
    p = tmp_path / "e.yaml"
    p.write_text(
        "pairs:\n"
        "  - id: x\n    question: q\n    deadline: '2027-01-01T00:00:00Z'\n"
        "    verified: true\n    checked_on: '2026-02-01'\n"
        "    checked_by: tester\n    legs:\n"
        "      - {venue: kalshi, key: A, side: 'yes'}\n"
        "      - {venue: polymarket, key: '1', side: 'yes'}\n",
        encoding="utf-8")
    from pmlab.archive import iter_snapshots
    j = basis.BasisJoin(basis.load_pairs(p))
    for s in iter_snapshots(data):
        j.observe(s)
    rep = j.report()
    assert rep["empty"] is False
    assert rep["pairs_verified"] == 1
    row = rep["pairs"][0]
    assert row["observations"] == 24
    # Kalshi mid 0.70, Polymarket mid 0.60 -> a constant 10-cent basis.
    assert row["basis_cents"]["median"] == pytest.approx(10.0)
    assert row["basis_cents"]["p10"] == pytest.approx(10.0)
    assert row["basis_cents"]["share_positive"] == pytest.approx(1.0)
    # b->a: buy Polymarket YES at 0.65, Kalshi NO at 1 - 0.65 = 0.35.
    # gross = 0.65 - 0.65 = 0.0; Kalshi charges
    # ceil(0.07 * 0.35 * 0.65) = ceil(0.0159) = 0.02 -> net -2 cents.
    assert row["edge_cents"]["net_median"] == pytest.approx(-2.0)
    assert row["edge_cents"]["snapshots_net_positive"] == 0
    # A constant basis has no decay, so no half-life is reported.
    assert row["half_life"]["half_life_hours"] is None


def test_a_pair_whose_legs_are_not_in_the_catalog_says_so(tmp_path):
    data = tmp_path / "data"
    write_snapshot(data / "20260208" / "1200Z.json.gz",
                   "2026-02-08T12:00:00Z", [poly("other", 0.45, 0.55)])
    p = tmp_path / "e.yaml"
    p.write_text(
        "pairs:\n"
        "  - id: ghost\n    verified: true\n    checked_on: '2026-02-01'\n"
        "    legs:\n"
        "      - {venue: kalshi, key: NOPE}\n"
        "      - {venue: polymarket, key: 'ALSO-NOPE'}\n", encoding="utf-8")
    from pmlab.archive import iter_snapshots
    j = basis.BasisJoin(basis.load_pairs(p))
    for s in iter_snapshots(data):
        j.observe(s)
    row = j.report()["pairs"][0]
    assert row["observations"] == 0
    assert "curation error" in row["reason"]
