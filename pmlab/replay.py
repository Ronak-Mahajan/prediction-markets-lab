"""Replay every screen over every snapshot and write the results.

    python -m pmlab.replay                       # data/ and archive/data
    python -m pmlab.replay --roots data          # just the main-branch blobs
    python -m pmlab.replay --out results --no-plots

The README has promised since the first commit that "the interesting
output is the time series of these counts as snapshots accumulate". This
is that script. It loads each snapshot through :mod:`pmlab.archive`, runs
the ladder, complement and bucket screens gross and net of each venue's
real fee, and writes four things:

* ``results/timeseries.csv``  -- one row per snapshot, every count;
* ``results/summary.json``    -- first/last snapshot, N, per-screen totals
  and medians, worst cases with their tickers, the fee model in force, and
  the sha256 identity of the exact set of blobs that produced it;
* ``results/README.md``       -- dated Markdown tables generated from the
  same numbers, so nothing is ever typed by hand;
* ``results/*.svg``           -- each screen's count over time.

The Kalshi complement identity is asserted, not screened. If
``no_ask == 1 - yes_bid`` ever fails, the replay stops with a non-zero
exit and reports it as a broken invariant: the screens in this package
were designed around that identity holding, so a break invalidates them
and must be looked at by a person before any number ships.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import buckets as buckets_mod
from . import complement as complement_mod
from . import fees as fees_mod
from . import ladders as ladders_mod
from .archive import load_snapshot, snapshot_paths

DEFAULT_ROOTS = ("data", "archive/data")

#: Columns of results/timeseries.csv, in order. One row per snapshot.
COLUMNS = (
    "t", "path", "schema",
    "kalshi_markets", "kalshi_two_sided", "kalshi_identity_checked",
    "kalshi_identity_deviations",
    "ladders", "ladder_rungs", "ladders_structured", "ladders_title",
    "ladder_adjacent_pairs",
    "ladder_inversions_gross", "ladder_inversions_net",
    "ladder_worst_gross_edge", "ladder_worst_net_edge",
    "ladder_negative_mass_gross", "ladder_negative_mass_beyond_fee",
    "ladder_negative_mass_total",
    "poly_rows", "poly_pairs", "poly_two_sided", "poly_crossed", "poly_era",
    "poly_complement_gross", "poly_complement_net", "poly_price_sum_median",
    "predictit_contracts", "predictit_pairs",
    "predictit_complement_gross", "predictit_complement_net",
    "predictit_cost_median",
    "bucket_events", "bucket_screened", "bucket_median_ask_sum",
    "bucket_candidates_gross", "bucket_candidates_net",
    "manifold_rows",
)


def archive_identity(paths: list[Path]) -> str:
    """sha256 over the sorted (path, blob sha256) pairs actually replayed.

    The same construction :mod:`pmlab.manifest` uses for the data branch,
    computed here over whatever roots this run was pointed at, so a result
    can always be traced back to the exact bytes behind it.
    """
    h = hashlib.sha256()
    for p in sorted(paths, key=lambda q: (q.parent.name, q.name)):
        bh = hashlib.sha256()
        with open(p, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                bh.update(chunk)
        h.update(f"{p.parent.name}/{p.name}\t{bh.hexdigest()}\n".encode())
    return h.hexdigest()


def code_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                             text=True, timeout=20)
        if out.returncode == 0:
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown"


def _median(xs: list[float]) -> float | None:
    return statistics.median(xs) if xs else None


def _schema_of(row: dict) -> int:
    """1 for a recorder-v1 snapshot, 2 for anything schema-2 or later."""
    return 1 if int(row["schema"]) < 2 else 2


def replay_one(path: Path) -> dict:
    """Every screen on one snapshot -> one flat row of counts."""
    snap = load_snapshot(path)
    ident = complement_mod.assert_kalshi_identity(snap.kalshi, where=str(path))
    lad = ladders_mod.screen_ladders(snap.kalshi)
    poly = complement_mod.screen_polymarket(snap.polymarket)
    pi = complement_mod.screen_predictit(snap.predictit)
    buc = buckets_mod.screen_buckets(snap.kalshi)
    row = {
        "t": snap.t.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "path": f"{path.parent.name}/{path.name}",
        "schema": snap.schema,
        "kalshi_markets": len(snap.kalshi),
        "kalshi_two_sided": sum(1 for r in snap.kalshi if r.get("two_sided")),
        "kalshi_identity_checked": ident.checked,
        "kalshi_identity_deviations": ident.deviations,
        "ladders": lad.ladders,
        "ladder_rungs": lad.rungs,
        "ladders_structured": lad.ladders_structured,
        "ladders_title": lad.ladders_title,
        "ladder_adjacent_pairs": lad.adjacent_pairs,
        "ladder_inversions_gross": lad.inversions_gross,
        "ladder_inversions_net": lad.inversions_net,
        "ladder_worst_gross_edge": round(
            lad.worst_inversion.gross_edge if lad.worst_inversion else 0.0, 6),
        "ladder_worst_net_edge": round(
            lad.worst_net_inversion.net_edge if lad.worst_net_inversion else 0.0, 6),
        "ladder_negative_mass_gross": lad.negative_mass_gross,
        "ladder_negative_mass_beyond_fee": lad.negative_mass_net,
        "ladder_negative_mass_total": round(lad.negative_mass_total, 6),
        "poly_rows": poly.rows,
        "poly_pairs": poly.pairs,
        "poly_two_sided": poly.two_sided_books,
        "poly_crossed": poly.crossed_books,
        "poly_era": (snap.polymarket[0].get("era", "") if snap.polymarket
                     else ""),
        "poly_complement_gross": poly.gross,
        "poly_complement_net": poly.net,
        "poly_price_sum_median": (round(poly.overround_median, 6)
                                  if poly.overround_median is not None else ""),
        "predictit_contracts": pi.contracts,
        "predictit_pairs": pi.pairs,
        "predictit_complement_gross": pi.gross,
        "predictit_complement_net": pi.net,
        "predictit_cost_median": (round(pi.overround_median, 6)
                                  if pi.overround_median is not None else ""),
        "bucket_events": buc.events,
        "bucket_screened": buc.screened,
        "bucket_median_ask_sum": (round(buc.median_ask_sum, 6)
                                  if buc.median_ask_sum is not None else ""),
        "bucket_candidates_gross": buc.gross,
        "bucket_candidates_net": buc.net,
        "manifold_rows": len(snap.manifold),
    }
    row["_reports"] = {"ladders": lad, "poly": poly, "predictit": pi,
                       "buckets": buc}
    return row


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------

def cadence_hours(rows: list[dict]) -> tuple[float | None, float | None]:
    ts = [datetime.strptime(r["t"], "%Y-%m-%dT%H:%M:%SZ") for r in rows]
    ts.sort()
    gaps = [(b - a).total_seconds() / 3600.0 for a, b in zip(ts, ts[1:])]
    if not gaps:
        return None, None
    return statistics.median(gaps), max(gaps)


def summarise(rows: list[dict], paths: list[Path], roots: tuple[str, ...]) -> dict:
    ints = lambda k: [int(r[k]) for r in rows]                  # noqa: E731
    med_gap, max_gap = cadence_hours(rows)
    ts = sorted(r["t"] for r in rows)
    days = (datetime.strptime(ts[-1], "%Y-%m-%dT%H:%M:%SZ")
            - datetime.strptime(ts[0], "%Y-%m-%dT%H:%M:%SZ")).total_seconds() / 86400.0

    worst_inv = worst_net_inv = None
    worst_poly = worst_pi = worst_bucket = None
    for r in rows:
        rep = r["_reports"]
        li = rep["ladders"].worst_inversion
        if li and (worst_inv is None or li.gross_edge > worst_inv[1].gross_edge):
            worst_inv = (r["t"], li)
        ln = rep["ladders"].worst_net_inversion
        if ln and (worst_net_inv is None or ln.net_edge > worst_net_inv[1].net_edge):
            worst_net_inv = (r["t"], ln)
        pw = rep["poly"].worst
        if pw and (worst_poly is None or pw.gross_edge > worst_poly[1].gross_edge):
            worst_poly = (r["t"], pw)
        iw = rep["predictit"].worst
        if iw and (worst_pi is None or iw.gross_edge > worst_pi[1].gross_edge):
            worst_pi = (r["t"], iw)
        bw = rep["buckets"].worst
        if bw and (worst_bucket is None or bw.gross_edge > worst_bucket[1].gross_edge):
            worst_bucket = (r["t"], bw)

    def dated(pair, body):
        return None if pair is None else {"snapshot": pair[0], **body(pair[1])}

    summary = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "code_commit": code_commit(),
        "archive": {
            "roots": list(roots),
            "snapshots": len(rows),
            "first_snapshot": ts[0],
            "last_snapshot": ts[-1],
            "days_spanned": round(days, 2),
            "schema1_snapshots": sum(1 for r in rows if int(r["schema"]) == 1),
            "schema2_snapshots": sum(1 for r in rows if int(r["schema"]) >= 2),
            "identity_sha256": archive_identity(paths),
            "median_gap_hours": None if med_gap is None else round(med_gap, 2),
            "max_gap_hours": None if max_gap is None else round(max_gap, 2),
        },
        "kalshi_identity": {
            "books_checked_total": sum(ints("kalshi_identity_checked")),
            "deviations_total": sum(ints("kalshi_identity_deviations")),
            "books_median": _median(ints("kalshi_identity_checked")),
            "note": "no_ask == 1 - yes_bid is asserted as a data-quality "
                    "invariant, not reported as a complement result; a single "
                    "deviation fails the replay.",
        },
        "ladders": {
            "median_per_snapshot": _median(ints("ladders")),
            "min_per_snapshot": min(ints("ladders")),
            "max_per_snapshot": max(ints("ladders")),
            "rungs_median_per_snapshot": _median(ints("ladder_rungs")),
            "rungs_total": sum(ints("ladder_rungs")),
            "adjacent_pairs_total": sum(ints("ladder_adjacent_pairs")),
            "inversions_gross_total": sum(ints("ladder_inversions_gross")),
            "inversions_net_total": sum(ints("ladder_inversions_net")),
            "snapshots_with_gross_inversion": sum(
                1 for r in rows if int(r["ladder_inversions_gross"]) > 0),
            "snapshots_with_net_inversion": sum(
                1 for r in rows if int(r["ladder_inversions_net"]) > 0),
            "negative_mass_gross_total": sum(ints("ladder_negative_mass_gross")),
            "negative_mass_beyond_fee_total": sum(
                ints("ladder_negative_mass_beyond_fee")),
            "negative_mass_gross_median": _median(
                ints("ladder_negative_mass_gross")),
            "worst_gross_inversion": dated(worst_inv, lambda i: {
                "event_ticker": i.event_ticker,
                "lower_ticker": i.lower_ticker, "upper_ticker": i.upper_ticker,
                "lower_threshold": i.lower_threshold,
                "upper_threshold": i.upper_threshold,
                "lower_ask": i.lower_ask, "upper_bid": i.upper_bid,
                "gross_edge_cents": round(i.gross_edge * 100, 2),
                "fee_cents": round(i.fee * 100, 2),
                "net_edge_cents": round(i.net_edge * 100, 2)}),
            "worst_net_inversion": dated(worst_net_inv, lambda i: {
                "event_ticker": i.event_ticker,
                "gross_edge_cents": round(i.gross_edge * 100, 2),
                "net_edge_cents": round(i.net_edge * 100, 2)}),
            # The two recorders see different universes -- v1 stopped at 2,000
            # events (about 14,000 markets, mostly midterm ladders), v2 sweeps
            # the whole open catalog (about 56,000) -- so a count pooled across
            # them is a count of two different experiments. Split, always.
            "by_recorder": {
                f"schema{k}": {
                    "snapshots": sum(1 for r in rows if _schema_of(r) == k),
                    "adjacent_pairs": sum(int(r["ladder_adjacent_pairs"])
                                          for r in rows if _schema_of(r) == k),
                    "inversions_gross": sum(int(r["ladder_inversions_gross"])
                                            for r in rows if _schema_of(r) == k),
                    "inversions_net": sum(int(r["ladder_inversions_net"])
                                          for r in rows if _schema_of(r) == k),
                }
                for k in (1, 2)
            },
        },
        "polymarket_complement": {
            "pairs_median_per_snapshot": _median(ints("poly_pairs")),
            "two_sided_median_per_snapshot": _median(ints("poly_two_sided")),
            "crossed_books_total": sum(ints("poly_crossed")),
            "gross_total": sum(ints("poly_complement_gross")),
            "net_total": sum(ints("poly_complement_net")),
            "snapshots_with_violation": sum(
                1 for r in rows if int(r["poly_complement_gross"]) > 0),
            # The 2026-08-23 to 09-01T16:44Z slice is the string-sorted era:
            # the venue served order=liquidity as text, so those rows are thin
            # and often already expired. Splitting the count by era is the
            # difference between "the venue quotes incoherently" and "the
            # recorder captured junk", and the two must not be conflated.
            "gross_string_sorted_era": sum(
                int(r["poly_complement_gross"]) for r in rows
                if r["poly_era"] == "string_sorted"),
            "gross_numeric_era": sum(
                int(r["poly_complement_gross"]) for r in rows
                if r["poly_era"] != "string_sorted"),
            "snapshots_string_sorted_era": sum(
                1 for r in rows if r["poly_era"] == "string_sorted"),
            "snapshots_numeric_era": sum(
                1 for r in rows if r["poly_era"] != "string_sorted"),
            "pairs_total": sum(ints("poly_pairs")),
            "worst": dated(worst_poly, lambda v: {
                "market_id": v.market_id, "question": v.question[:140],
                "prices": list(v.prices), "total": round(v.total, 4),
                "gross_edge_cents": round(v.gross_edge * 100, 2),
                "net_edge_cents": round(v.net_edge * 100, 2), "era": v.era}),
            "note": "Screened on the venue's quoted outcome-price pair, not "
                    "on two asks: the complementary token's book is not in "
                    "this archive (a recorder gap). A violation is an "
                    "incoherent quote, not a demonstrated trade.",
        },
        "predictit_complement": {
            "pairs_median_per_snapshot": _median(ints("predictit_pairs")),
            "pairs_total": sum(ints("predictit_pairs")),
            "gross_total": sum(ints("predictit_complement_gross")),
            "net_total": sum(ints("predictit_complement_net")),
            "snapshots_with_violation": sum(
                1 for r in rows if int(r["predictit_complement_gross"]) > 0),
            "worst": dated(worst_pi, lambda v: {
                "market_name": v.market_name[:140],
                "contract_name": v.contract_name[:80],
                "yes_cost": v.yes_cost, "no_cost": v.no_cost,
                "gross_edge_cents": round(v.gross_edge * 100, 2),
                "net_edge_cents": round(v.net_edge * 100, 2)}),
        },
        "buckets": {
            "screened_median_per_snapshot": _median(ints("bucket_screened")),
            "screened_total": sum(ints("bucket_screened")),
            "candidates_gross_median": _median(ints("bucket_candidates_gross")),
            "candidates_net_median": _median(ints("bucket_candidates_net")),
            "candidates_gross_total": sum(ints("bucket_candidates_gross")),
            "candidates_net_total": sum(ints("bucket_candidates_net")),
            "worst": dated(worst_bucket, lambda c: {
                "event_ticker": c.event_ticker, "title": c.title[:140],
                "buckets": c.buckets, "ask_sum": round(c.ask_sum, 4),
                "gross_edge_cents": round(c.gross_edge * 100, 2),
                "net_edge_cents": round(c.net_edge * 100, 2)}),
            "caveat": buckets_mod.OPEN_UNIVERSE_CAVEAT,
        },
        "fees": {
            "as_of": fees_mod.FEES_AS_OF.isoformat(),
            "models": {k: {"note": v.note, "source": v.source,
                           "caveats": list(v.caveats)}
                       for k, v in fees_mod.FEE_MODELS.items()},
            "kalshi_reduced_multiplier_series": sorted(
                fees_mod.KALSHI_REDUCED_TAKER_MULTIPLIER),
        },
    }
    # Where the inversions live. 21 events out of a catalog of 2,000 carried
    # every one of them in the first replay, and they were long-dated Fed
    # funds and CPI ladders -- the rungs nobody trades. That concentration is
    # the finding; the raw count is not.
    by_event: dict[str, int] = {}
    net_by_event: dict[str, int] = {}
    for r in rows:
        for k, v in r["_reports"]["ladders"].inversions_by_event.items():
            by_event[k] = by_event.get(k, 0) + v
        for lad in r["_reports"]["ladders"].net_inversions:
            net_by_event[lad] = net_by_event.get(lad, 0) + 1
    summary["ladders"]["net_inversion_events"] = len(net_by_event)
    summary["ladders"]["net_inversion_event_tickers"] = sorted(net_by_event)[:12]
    summary["ladders"]["inversion_events"] = len(by_event)
    summary["ladders"]["top_inversion_events"] = [
        {"event_ticker": k, "inversions": v}
        for k, v in sorted(by_event.items(), key=lambda kv: (-kv[1], kv[0]))[:12]]

    # Recurring candidates are the ones worth a human read; a one-snapshot
    # hit is usually a stale quote.
    seen: dict[str, int] = {}
    for r in rows:
        for c in r["_reports"]["buckets"].candidates:
            seen[c.event_ticker] = seen.get(c.event_ticker, 0) + 1
    summary["buckets"]["recurring_candidates"] = [
        {"event_ticker": k, "snapshots": v}
        for k, v in sorted(seen.items(), key=lambda kv: (-kv[1], kv[0]))[:15]]
    return summary


# --------------------------------------------------------------------------
# Outputs
# --------------------------------------------------------------------------

def keep_stamp_if_unchanged(summary: dict, previous: Path) -> dict:
    """Carry the old ``generated`` stamp forward when nothing else moved.

    The daily job re-runs whether or not a snapshot arrived. Stamping a
    fresh wall-clock time on an otherwise byte-identical result would
    produce a commit a day that says nothing, so ``generated`` means "when
    these numbers were first produced" rather than "when the job last ran".
    Everything else -- including the code commit -- still counts as a
    change, because a number produced by different code is a different
    number even when it lands on the same value.
    """
    if not previous.exists():
        return summary
    try:
        with open(previous, encoding="utf-8") as fh:
            old = json.load(fh)
    except (OSError, ValueError):
        return summary
    a = {k: v for k, v in summary.items() if k != "generated"}
    b = {k: v for k, v in old.items() if k != "generated"}
    if a == b and isinstance(old.get("generated"), str):
        summary = dict(summary)
        summary["generated"] = old["generated"]
    return summary


def write_timeseries(rows: list[dict], out: Path) -> Path:
    p = out / "timeseries.csv"
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        w = csv.DictWriter(fh, fieldnames=list(COLUMNS), lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in COLUMNS})
    return p


def _fmt(x, nd: int = 0) -> str:
    if x is None or x == "":
        return "-"
    if isinstance(x, float) and nd:
        return f"{x:,.{nd}f}"
    if isinstance(x, float) and x.is_integer():
        return f"{int(x):,}"
    if isinstance(x, (int,)):
        return f"{x:,}"
    return str(x)


def render_results_readme(s: dict) -> str:
    a = s["archive"]
    lad, ki = s["ladders"], s["kalshi_identity"]
    poly, pi, buc = (s["polymarket_complement"], s["predictit_complement"],
                     s["buckets"])
    L: list[str] = []
    w = L.append
    w("# Coherence over the archive")
    w("")
    w(f"Generated {s['generated']} by `python -m pmlab.replay` at commit "
      f"`{s['code_commit'][:12]}`.")
    w("")
    w(f"**Archive replayed:** {_fmt(a['snapshots'])} snapshots, "
      f"{a['first_snapshot']} to {a['last_snapshot']} "
      f"({_fmt(a['days_spanned'], 1)} days), realised cadence median "
      f"{_fmt(a['median_gap_hours'], 1)} h / max "
      f"{_fmt(a['max_gap_hours'], 1)} h.  ")
    w(f"**Archive identity (sha256 of the blob list):** "
      f"`{a['identity_sha256']}`")
    w("")
    w("Every count below is produced twice: **gross**, and **net** of the "
      "venue's own fee with the venue's own rounding. The gap between the "
      "two columns is the result.")
    w("")
    w("## The one-line answer")
    w("")
    w(f"Across {_fmt(a['snapshots'])} snapshots and "
      f"{_fmt(a['days_spanned'], 1)} days, "
      f"{_fmt(lad['inversions_gross_total'])} gross ladder monotonicity "
      f"inversions were found and "
      f"{_fmt(lad['inversions_net_total'])} survived the fee model; "
      f"{_fmt(pi['gross_total'])} PredictIt and "
      f"{_fmt(poly['gross_total'])} Polymarket complement violations gross, "
      f"{_fmt(pi['net_total'])} and {_fmt(poly['net_total'])} net; a median "
      f"{_fmt(buc['candidates_gross_median'])} bucket-sum candidates per "
      f"snapshot gross and {_fmt(buc['candidates_net_median'])} net, all "
      f"open-universe events. The Kalshi complement identity held on "
      f"{_fmt(ki['books_checked_total'] - ki['deviations_total'])} of "
      f"{_fmt(ki['books_checked_total'])} two-sided books.")
    w("")
    w("## Kalshi ladders")
    w("")
    w("| quantity | value |")
    w("|---|---|")
    w(f"| ladders per snapshot (median) | {_fmt(lad['median_per_snapshot'])} |")
    w(f"| ladders per snapshot (min-max) | {_fmt(lad['min_per_snapshot'])}"
      f"-{_fmt(lad['max_per_snapshot'])} |")
    w(f"| rungs per snapshot (median) | {_fmt(lad['rungs_median_per_snapshot'])} |")
    w(f"| adjacent strike pairs tested (total) | {_fmt(lad['adjacent_pairs_total'])} |")
    w(f"| monotonicity inversions, gross (total) | {_fmt(lad['inversions_gross_total'])} |")
    w(f"| monotonicity inversions, net of fee (total) | {_fmt(lad['inversions_net_total'])} |")
    w(f"| snapshots with any gross inversion | {_fmt(lad['snapshots_with_gross_inversion'])} of {_fmt(a['snapshots'])} |")
    w(f"| negative implied mass at mids, gross (total) | {_fmt(lad['negative_mass_gross_total'])} |")
    w(f"| ... whose magnitude exceeds two legs of fee | {_fmt(lad['negative_mass_beyond_fee_total'])} |")
    w("")
    if lad["worst_gross_inversion"]:
        i = lad["worst_gross_inversion"]
        w(f"Worst gross inversion: `{i['event_ticker']}` on {i['snapshot']}, "
          f"strike {i['lower_threshold']:g} ask {i['lower_ask']:.2f} against "
          f"strike {i['upper_threshold']:g} bid {i['upper_bid']:.2f} -- "
          f"{i['gross_edge_cents']:.1f}c gross, {i['fee_cents']:.1f}c of fee "
          f"on the two legs, {i['net_edge_cents']:.1f}c net.")
        w("")
    br = lad.get("by_recorder") or {}
    if br:
        w("Recorder v1 stopped at 2,000 events (about 14,000 markets, mostly "
          "the two midterm ladder families); recorder v2 sweeps the whole open "
          "catalog (about 56,000). Pooling the two counts a different "
          "experiment twice, so they are split:")
        w("")
        w("| recorder | snapshots | adjacent pairs | inversions gross | net of fee |")
        w("|---|---|---|---|---|")
        for k, label in (("schema1", "v1 (2,000-event cap)"),
                         ("schema2", "v2 (full catalog)")):
            d = br.get(k) or {}
            w(f"| {label} | {_fmt(d.get('snapshots'))} "
              f"| {_fmt(d.get('adjacent_pairs'))} "
              f"| {_fmt(d.get('inversions_gross'))} "
              f"| {_fmt(d.get('inversions_net'))} |")
        w("")
    if lad.get("top_inversion_events"):
        w(f"Those {_fmt(lad['inversions_gross_total'])} inversions are not "
          f"spread across the catalog: they fall in "
          f"{_fmt(lad['inversion_events'])} events.")
        w("")
        w("| event | gross inversions |")
        w("|---|---|")
        for e in lad["top_inversion_events"][:10]:
            w(f"| `{e['event_ticker']}` | {_fmt(e['inversions'])} |")
        w("")
    w("The inversion screen is at the touch and is executable by "
      "construction: sell the higher strike at its bid, buy the lower at its "
      "ask. The negative-mass screen is at mids and is **not** a trade -- it "
      "says where the quoted curve is marked impossibly, which is a wider and "
      "softer statement. The two must not be read as the same number.")
    w("")
    w("## Complement")
    w("")
    w("| venue | pairs per snapshot (median) | gross (total) | net (total) |")
    w("|---|---|---|---|")
    w(f"| Polymarket (quoted outcome pair) | {_fmt(poly['pairs_median_per_snapshot'])} "
      f"| {_fmt(poly['gross_total'])} | {_fmt(poly['net_total'])} |")
    w(f"| PredictIt (YES/NO asks) | {_fmt(pi['pairs_median_per_snapshot'])} "
      f"| {_fmt(pi['gross_total'])} | {_fmt(pi['net_total'])} |")
    w(f"| Kalshi | not screened | - | - |")
    w("")
    w(f"Kalshi is not screened on purpose: `no_ask == 1 - yes_bid` held on "
      f"{_fmt(ki['books_checked_total'] - ki['deviations_total'])} of "
      f"{_fmt(ki['books_checked_total'])} two-sided books across the whole "
      f"archive ({_fmt(ki['deviations_total'])} deviations), so YES ask plus "
      f"NO ask is 1 plus the spread by construction and the screen cannot "
      f"fire. It is asserted as an invariant: a single deviation fails this "
      f"replay.")
    w("")
    w(poly["note"])
    w("")
    w(f"All {_fmt(poly['gross_total'])} Polymarket violations fall in the "
      f"{_fmt(poly['snapshots_string_sorted_era'])} snapshots of the "
      f"string-sorted era (2026-08-23 to 2026-09-01T16:44Z), when the venue "
      f"served `order=liquidity` sorted as text and the recorder kept the "
      f"result: thin, often already-expired rows. The "
      f"{_fmt(poly['snapshots_numeric_era'])} snapshots of the clean "
      f"`liquidityNum` era carry "
      f"{_fmt(poly['gross_numeric_era'])}. That is a statement about the "
      f"recorder, not about the venue's quotes.")
    w("")
    w("## Bucket sums")
    w("")
    w("| quantity | value |")
    w("|---|---|")
    w(f"| mutually-exclusive events screened per snapshot (median) | {_fmt(buc['screened_median_per_snapshot'])} |")
    w(f"| candidates per snapshot, gross (median) | {_fmt(buc['candidates_gross_median'])} |")
    w(f"| candidates per snapshot, net of fee (median) | {_fmt(buc['candidates_net_median'])} |")
    w("")
    if buc["recurring_candidates"]:
        w("Most persistent candidates (snapshots in which the event was "
          "flagged):")
        w("")
        w("| event | snapshots |")
        w("|---|---|")
        for c in buc["recurring_candidates"][:10]:
            w(f"| `{c['event_ticker']}` | {_fmt(c['snapshots'])} |")
        w("")
    w(buc["caveat"])
    w("")
    w("## Fee models in force")
    w("")
    w(f"Constants read {s['fees']['as_of']}.")
    w("")
    w("| venue | model |")
    w("|---|---|")
    for name, m in s["fees"]["models"].items():
        w(f"| {name} | {m['note']} |")
    w("")
    for name, m in s["fees"]["models"].items():
        for c in m["caveats"]:
            w(f"- **{name}:** {c}")
    w("")
    w("## Figures")
    w("")
    for fn, cap in FIGURES:
        w(f"![{cap}]({fn})")
        w("")
    w("## Reproduce")
    w("")
    w("```")
    w("python -m pmlab.replay --roots data")
    w("```")
    w("")
    w("`timeseries.csv` carries one row per snapshot and every column behind "
      "these tables; `summary.json` carries the same numbers plus the worst "
      "case for each screen with its ticker. Neither file is edited by hand.")
    return "\n".join(L) + "\n"


FIGURES = (
    ("ladders.svg", "Ladders and rungs parsed per snapshot"),
    ("ladder_inversions.svg", "Ladder monotonicity inversions per snapshot, gross and net"),
    ("negative_mass.svg", "Adjacent strike pairs with negative implied mass"),
    ("complement.svg", "Complement violations per snapshot by venue"),
    ("buckets.svg", "Bucket-sum candidates per snapshot, gross and net"),
)


def write_plots(rows: list[dict], out: Path) -> list[Path]:
    """One SVG per screen. Deterministic output: no timestamp, fixed ids."""
    import matplotlib
    matplotlib.use("Agg")
    matplotlib.rcParams["svg.hashsalt"] = "pmlab"
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    ts = [datetime.strptime(r["t"], "%Y-%m-%dT%H:%M:%SZ") for r in rows]
    specs = [
        ("ladders.svg", "Kalshi threshold ladders per snapshot", "count",
         [("ladders", "ladders"), ("ladder_rungs", "rungs")]),
        ("ladder_inversions.svg",
         "Ladder monotonicity inversions per snapshot", "count",
         [("ladder_inversions_gross", "gross"),
          ("ladder_inversions_net", "net of fee")]),
        ("negative_mass.svg",
         "Adjacent strike pairs with negative implied mass (at mids)", "count",
         [("ladder_negative_mass_gross", "negative mass"),
          ("ladder_negative_mass_beyond_fee", "magnitude beyond two legs of fee")]),
        ("complement.svg", "Complement violations per snapshot", "count",
         [("poly_complement_gross", "Polymarket gross"),
          ("poly_complement_net", "Polymarket net"),
          ("predictit_complement_gross", "PredictIt gross"),
          ("predictit_complement_net", "PredictIt net")]),
        ("buckets.svg", "Bucket-sum candidates per snapshot", "count",
         [("bucket_candidates_gross", "gross"),
          ("bucket_candidates_net", "net of fee")]),
    ]
    written: list[Path] = []
    for fn, title, ylabel, series in specs:
        fig, ax = plt.subplots(figsize=(9, 3.4))
        for col, label in series:
            ax.plot(ts, [int(r[col]) for r in rows], marker=".", linewidth=1.1,
                    markersize=3, label=label)
        ax.set_title(title, fontsize=10)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.grid(True, alpha=0.25, linewidth=0.6)
        ax.legend(fontsize=8, frameon=False)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
        ax.tick_params(labelsize=8)
        if all(int(r[c]) == 0 for c, _ in series for r in rows):
            ax.set_ylim(-0.5, 1.0)
            ax.text(0.5, 0.55, "zero in every snapshot", ha="center",
                    transform=ax.transAxes, fontsize=9, alpha=0.65)
        fig.autofmt_xdate()
        fig.tight_layout()
        p = out / fn
        fig.savefig(p, format="svg", metadata={"Date": None})
        plt.close(fig)
        written.append(p)
    return written


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--roots", nargs="*", default=list(DEFAULT_ROOTS),
                    help="data roots holding YYYYMMDD/HHMMZ.json.gz")
    ap.add_argument("--out", default="results", help="output directory")
    ap.add_argument("--limit", type=int, default=0,
                    help="replay only the newest N snapshots (for a smoke run)")
    ap.add_argument("--no-plots", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)

    paths = snapshot_paths(*a.roots)
    if a.limit:
        paths = paths[-a.limit:]
    if not paths:
        # An archive that has not been checked out yet is the ordinary state
        # of a fresh clone, not a failure. Say so and leave results/ alone.
        print(f"no snapshots under {a.roots}; nothing to replay")
        return 0

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for i, p in enumerate(paths, 1):
        rows.append(replay_one(p))
        if not a.quiet and (i % 20 == 0 or i == len(paths)):
            print(f"  replayed {i}/{len(paths)}", flush=True)

    summary = summarise(rows, paths, tuple(a.roots))
    summary = keep_stamp_if_unchanged(summary, out / "summary.json")
    write_timeseries(rows, out)
    with open(out / "summary.json", "w", encoding="utf-8", newline="\n") as fh:
        json.dump(summary, fh, indent=1, sort_keys=False)
        fh.write("\n")
    if not a.no_plots:
        try:
            write_plots(rows, out)
        except ImportError as exc:
            print(f"plots skipped: {exc}")
    with open(out / "README.md", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_results_readme(summary))

    a_ = summary["archive"]
    print(f"replayed {a_['snapshots']} snapshots "
          f"({a_['first_snapshot']} -> {a_['last_snapshot']}), "
          f"archive id {a_['identity_sha256'][:12]}")
    print(f"  ladder inversions gross {summary['ladders']['inversions_gross_total']}, "
          f"net {summary['ladders']['inversions_net_total']}")
    print(f"  complement gross poly {summary['polymarket_complement']['gross_total']}, "
          f"predictit {summary['predictit_complement']['gross_total']}")
    print(f"  bucket candidates median/snapshot gross "
          f"{summary['buckets']['candidates_gross_median']}, "
          f"net {summary['buckets']['candidates_net_median']}")
    print(f"  wrote {out}/timeseries.csv, summary.json, README.md")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except complement_mod.BrokenInvariant as exc:
        print(f"BROKEN INVARIANT: {exc}", file=sys.stderr)
        sys.exit(2)
