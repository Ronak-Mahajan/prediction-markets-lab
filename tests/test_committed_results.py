"""Do the committed numbers reproduce from the committed rows?

Every other test in this suite checks the code against hand-computed
answers. This one checks the *published files* against each other, and it
does it without importing pmlab: `summary.json` is recomputed from
`timeseries.csv` and the calibration headline from `calibration.csv`,
using nothing but csv, math and statistics. If the summary were merely
echoing the code that wrote the rows, these assertions would pass
trivially and prove nothing -- so they deliberately re-derive the
aggregate a second time, by hand, from the per-snapshot and per-forecast
rows a reader can open in a spreadsheet.

That is what makes "every headline number ships with the code that
produced it" checkable by a stranger: the rows are in the repository, the
arithmetic is below, and it runs on every push.

Precision. `calibration.csv` writes prices to six decimal places, so a
mean over thousands of rows recomputed from it agrees with the summary to
about 1e-9 rather than exactly. Measured on the 2026-09-11 archive: the
Brier score agrees to 3.1e-10 and the mean mid to 1.4e-9. The tolerances
below are set just above that, not at "whatever passes".
"""
from __future__ import annotations

import csv
import json
import math
import statistics
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"

#: Six decimal places in the CSV against a mean over thousands of rows.
CSV_ROUNDING_TOLERANCE = 1e-8


def _results():
    if not (RESULTS / "summary.json").exists():
        pytest.skip("no results committed yet")
    with open(RESULTS / "summary.json", encoding="utf-8") as fh:
        summary = json.load(fh)
    with open(RESULTS / "timeseries.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return summary, rows


def _median(xs):
    return statistics.median(xs) if xs else None


# --------------------------------------------------------------------------
# summary.json against timeseries.csv
# --------------------------------------------------------------------------

def test_the_archive_block_reproduces_from_the_rows():
    summary, rows = _results()
    a = summary["archive"]
    assert a["snapshots"] == len(rows)
    ts = sorted(r["t"] for r in rows)
    assert a["first_snapshot"] == ts[0]
    assert a["last_snapshot"] == ts[-1]
    assert a["schema1_snapshots"] == sum(1 for r in rows if int(r["schema"]) == 1)
    assert a["schema2_snapshots"] == sum(1 for r in rows if int(r["schema"]) >= 2)
    assert a["schema1_snapshots"] + a["schema2_snapshots"] == len(rows)
    t = sorted(datetime.strptime(r["t"], "%Y-%m-%dT%H:%M:%SZ") for r in rows)
    gaps = [(y - x).total_seconds() / 3600.0 for x, y in zip(t, t[1:])]
    if gaps:
        assert a["median_gap_hours"] == pytest.approx(_median(gaps), abs=0.005)
        assert a["max_gap_hours"] == pytest.approx(max(gaps), abs=0.005)
    days = (t[-1] - t[0]).total_seconds() / 86400.0
    assert a["days_spanned"] == pytest.approx(days, abs=0.005)


@pytest.mark.parametrize("key,column", [
    ("ladders.rungs_total", "ladder_rungs"),
    ("ladders.adjacent_pairs_total", "ladder_adjacent_pairs"),
    ("ladders.inversions_gross_total", "ladder_inversions_gross"),
    ("ladders.inversions_net_total", "ladder_inversions_net"),
    ("ladders.negative_mass_gross_total", "ladder_negative_mass_gross"),
    ("ladders.negative_mass_beyond_fee_total", "ladder_negative_mass_beyond_fee"),
    ("kalshi_identity.books_checked_total", "kalshi_identity_checked"),
    ("kalshi_identity.deviations_total", "kalshi_identity_deviations"),
    ("polymarket_complement.pairs_total", "poly_pairs"),
    ("polymarket_complement.gross_total", "poly_complement_gross"),
    ("polymarket_complement.net_total", "poly_complement_net"),
    ("polymarket_complement.crossed_books_total", "poly_crossed"),
    ("predictit_complement.pairs_total", "predictit_pairs"),
    ("predictit_complement.gross_total", "predictit_complement_gross"),
    ("predictit_complement.net_total", "predictit_complement_net"),
    ("buckets.screened_total", "bucket_screened"),
    ("buckets.candidates_gross_total", "bucket_candidates_gross"),
    ("buckets.candidates_net_total", "bucket_candidates_net"),
])
def test_a_published_total_is_the_sum_of_the_published_rows(key, column):
    summary, rows = _results()
    node = summary
    for part in key.split("."):
        node = node[part]
    assert node == sum(int(r[column]) for r in rows), key


@pytest.mark.parametrize("key,column", [
    ("ladders.median_per_snapshot", "ladders"),
    ("buckets.screened_median_per_snapshot", "bucket_screened"),
    ("buckets.candidates_gross_median", "bucket_candidates_gross"),
    ("buckets.candidates_net_median", "bucket_candidates_net"),
    ("kalshi_identity.books_median", "kalshi_identity_checked"),
])
def test_a_published_median_is_the_median_of_the_published_rows(key, column):
    summary, rows = _results()
    node = summary
    for part in key.split("."):
        node = node[part]
    assert node == pytest.approx(_median([int(r[column]) for r in rows]))


def test_the_recorder_split_partitions_the_archive():
    """v1 and v2 see different catalogs, so the counts are split. A split
    that does not add up is a split that is hiding something."""
    summary, rows = _results()
    br = summary["ladders"]["by_recorder"]
    assert (br["schema1"]["snapshots"] + br["schema2"]["snapshots"]
            == len(rows))
    for field, column in (("adjacent_pairs", "ladder_adjacent_pairs"),
                          ("inversions_gross", "ladder_inversions_gross"),
                          ("inversions_net", "ladder_inversions_net")):
        assert (br["schema1"][field] + br["schema2"][field]
                == sum(int(r[column]) for r in rows)), field


def test_the_polymarket_era_split_partitions_the_archive():
    """The string-sorted era is a recorder defect, not a venue fact, and the
    whole point of the split is that a reader can see which is which."""
    summary, rows = _results()
    p = summary["polymarket_complement"]
    assert (p["snapshots_string_sorted_era"] + p["snapshots_numeric_era"]
            == len(rows))
    assert (p["gross_string_sorted_era"] + p["gross_numeric_era"]
            == p["gross_total"])


def test_net_never_exceeds_gross_in_any_row():
    """Charging a fee cannot create a violation. If this ever fails, the fee
    model has a sign error somewhere."""
    _, rows = _results()
    for r in rows:
        assert int(r["ladder_inversions_net"]) <= int(r["ladder_inversions_gross"])
        assert int(r["bucket_candidates_net"]) <= int(r["bucket_candidates_gross"])
        assert int(r["poly_complement_net"]) <= int(r["poly_complement_gross"])
        assert int(r["predictit_complement_net"]) <= int(r["predictit_complement_gross"])
        assert int(r["bucket_screened"]) <= int(r["bucket_events"])
        assert (int(r["ladder_negative_mass_beyond_fee"])
                <= int(r["ladder_negative_mass_gross"]))


def test_the_worst_case_in_the_summary_is_the_worst_case_in_the_rows():
    summary, rows = _results()
    lad = summary["ladders"]
    if lad["worst_gross_inversion"]:
        worst = max(float(r["ladder_worst_gross_edge"]) for r in rows)
        assert lad["worst_gross_inversion"]["gross_edge_cents"] == pytest.approx(
            worst * 100, abs=0.005)
    if lad["worst_net_inversion"]:
        worst = max(float(r["ladder_worst_net_edge"]) for r in rows)
        assert lad["worst_net_inversion"]["net_edge_cents"] == pytest.approx(
            worst * 100, abs=0.005)


# --------------------------------------------------------------------------
# the calibration headline against calibration.csv
# --------------------------------------------------------------------------

HEADLINE_VENUES = ("kalshi", "polymarket", "manifold")
LOG_CLIP = 1e-4


def _forecasts():
    summary, _ = _results()
    cal = summary["calibration"]
    if cal.get("empty") or not (RESULTS / "calibration.csv").exists():
        pytest.skip("nothing scored yet")
    with open(RESULTS / "calibration.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return cal, rows


def test_the_headline_brier_and_log_score_reproduce_from_the_forecast_rows():
    """Recomputed here with csv and math only. Agreement is to about 1e-9
    because the CSV writes six decimal places, not because either side is
    approximate."""
    cal, rows = _forecasts()
    h = cal["headline"]
    sel = [r for r in rows
           if r["horizon"] == cal["headline_horizon"]
           and r["venue"] in HEADLINE_VENUES and int(r["inferred"]) == 0]
    assert len(sel) == h["n"] > 0
    assert len({r["block"] for r in sel}) == h["blocks"]
    ps = [float(r["mid"]) for r in sel]
    ys = [float(r["outcome"]) for r in sel]
    brier = sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ps)
    assert h["brier"] == pytest.approx(brier, abs=CSV_ROUNDING_TOLERANCE)
    assert h["brier_skill_vs_5050"] == pytest.approx(
        1.0 - brier / 0.25, abs=CSV_ROUNDING_TOLERANCE)
    log = sum(math.log(min(max(p, LOG_CLIP), 1 - LOG_CLIP)) if y >= 0.5
              else math.log(1 - min(max(p, LOG_CLIP), 1 - LOG_CLIP))
              for p, y in zip(ps, ys)) / len(ps)
    assert h["log_score"] == pytest.approx(log, abs=CSV_ROUNDING_TOLERANCE)
    assert h["mean_mid"] == pytest.approx(
        sum(ps) / len(ps), abs=CSV_ROUNDING_TOLERANCE)
    assert h["base_rate"] == pytest.approx(
        sum(ys) / len(ys), abs=CSV_ROUNDING_TOLERANCE)


def test_every_horizon_count_reproduces_from_the_forecast_rows():
    cal, rows = _forecasts()
    for label, group in cal["by_horizon"].items():
        sel = [r for r in rows if r["horizon"] == label
               and r["venue"] in HEADLINE_VENUES and int(r["inferred"]) == 0]
        assert group["n"] == len(sel), label
    assert cal["observations"] == len(rows)
    assert cal["observations_headline"] == sum(
        1 for r in rows if int(r["inferred"]) == 0)


def test_inferred_outcomes_are_kept_out_of_every_headline_slice():
    """PredictIt outcomes are guessed from a vanished contract's last trade.
    Scoring a forecast against a guess is not a measurement, and the
    exclusion is the kind of thing that quietly stops being true."""
    cal, rows = _forecasts()
    inferred = [r for r in rows if int(r["inferred"]) == 1]
    assert all(r["venue"] not in HEADLINE_VENUES for r in inferred)
    assert cal["inferred_excluded_from_headline"] == len(inferred)


def test_the_outcome_join_is_not_upside_down():
    """The cheapest possible detector of joining an outcome to the wrong side
    of the book: markets that settled YES must have been quoted higher than
    markets that settled NO."""
    cal, rows = _forecasts()
    sel = [r for r in rows if r["horizon"] == cal["headline_horizon"]
           and r["venue"] in HEADLINE_VENUES and int(r["inferred"]) == 0]
    yes = [float(r["mid"]) for r in sel if float(r["outcome"]) >= 0.5]
    no = [float(r["mid"]) for r in sel if float(r["outcome"]) < 0.5]
    assert yes and no
    assert sum(yes) / len(yes) > sum(no) / len(no)
    mm = cal["mean_mid_by_outcome"]
    assert mm["settled_yes"] == pytest.approx(sum(yes) / len(yes), abs=5e-5)
    assert mm["settled_no"] == pytest.approx(sum(no) / len(no), abs=5e-5)


def test_every_scored_quote_is_a_two_sided_price_with_a_finite_mid():
    """bid > 0 and ask >= bid on every venue that runs a book, and the mid
    strictly inside (0, 1) so the log score is finite without clipping.

    The ask may be exactly $1.00 and often is: 285 of the 4,823 scored
    quotes on the 2026-09-11 archive (5.9%, 267 Kalshi and 18 Polymarket)
    are offered at a dollar, which is a real resting offer and not a
    tradeable one -- nobody pays $1 for something that pays at most $1.
    Those rows are honest two-sided quotes and their mids are 0.985-0.995,
    so they score normally; where they matter is the favourite-longshot
    table measured on the ask, which is exactly why that table reports a
    median spread per bin instead of filtering."""
    cal, rows = _forecasts()
    clipped = 0
    for r in rows:
        bid, ask, mid = float(r["bid"]), float(r["ask"]), float(r["mid"])
        assert 0.0 < bid <= ask <= 1.0, r["key"]
        assert mid == pytest.approx((bid + ask) / 2.0, abs=1e-6)
        assert 0.0 < mid < 1.0, r["key"]
        if not LOG_CLIP <= mid <= 1.0 - LOG_CLIP:
            clipped += 1
        assert float(r["outcome"]) in (0.0, 1.0)
    # The summary reports how often the log score had to clip; it must be
    # the number of rows that actually needed it.
    assert cal["headline"]["log_clipped"] <= clipped


def test_no_scored_quote_is_newer_than_its_horizon_allows():
    """The cut-off is `settled_at - H` and the quote may be at most 24 h
    older, so the gap between quote and settlement is bounded on both sides.
    A gap below the horizon means a quote from inside the cut-off leaked in."""
    cal, rows = _forecasts()
    horizons = {h["label"]: h["days"] for h in cal["horizons"]}
    cap = cal["max_quote_age_hours"]
    # quote_age_hours is written to three decimals, so allow the rounding.
    slack = 1e-3
    for r in rows:
        hours = float(r["quote_age_hours"])
        days = horizons[r["horizon"]]
        assert days * 24.0 - slack <= hours <= days * 24.0 + cap + slack, r["key"]
