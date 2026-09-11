"""Coherence report on ONE snapshot: a thin wrapper over pmlab.

    python screen.py                        # newest snapshot under data/
    python screen.py data/20260823/0118Z.json.gz
    python screen.py --archive archive      # also look at the data branch

Every screen this prints lives in :mod:`pmlab.ladders`,
:mod:`pmlab.complement` and :mod:`pmlab.buckets`, and is the same code the
archive-wide replay runs, so a number here and a number in ``results/``
can never disagree because two parsers drifted apart. What this script
adds is a readable single-snapshot view for the moment you want to know
what the venues look like *right now*.

The time series -- which is the output that actually answers anything --
is ``python -m pmlab.replay``.

Three constraints, each reported gross and net of the venue's own fee with
the venue's own rounding:

1. **Complement.** Buying both sides must cost at least $1. Screened on
   Polymarket's quoted outcome pair and on PredictIt's YES/NO asks. NOT
   screened on Kalshi, where ``no_ask == 1 - yes_bid`` makes it a
   tautology; that identity is asserted instead and a breach is an error.
2. **Bucket sums.** Mutually exclusive events whose asks sum below $1.
   Candidates, not arbitrages: the survivors are open-universe events
   whose listed buckets are not exhaustive.
3. **Ladder monotonicity.** P(>= s) must not increase with s. A higher
   strike bidding over a lower strike's ask is incoherence beyond the
   spread -- and, at one cent, is still two cents short of a trade.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pmlab import buckets as buckets_mod
from pmlab import complement as complement_mod
from pmlab import fees as fees_mod
from pmlab import ladders as ladders_mod
from pmlab.archive import load_snapshot, snapshot_paths

ROOT = Path(__file__).resolve().parent


def c(x: float) -> str:
    """Dollars as cents, the unit every venue in this archive quotes in."""
    return f"{x * 100:.1f}c"


def report(path: Path) -> int:
    snap = load_snapshot(path)
    print(f"snapshot {snap.t:%Y-%m-%dT%H:%M:%SZ}  schema {snap.schema}  {path}")
    for name in ("kalshi", "polymarket", "predictit", "manifold"):
        print(f"  {name}: {len(snap.venues.get(name, [])):,} rows")
    if snap.errors:
        print(f"  recorder errors: {snap.errors}")
    if not snap.kalshi:
        print("no kalshi rows in this snapshot", file=sys.stderr)

    print("\n[invariant] Kalshi no_ask == 1 - yes_bid")
    ident = complement_mod.kalshi_identity(snap.kalshi)
    print(f"  {ident.checked - ident.deviations:,} of {ident.checked:,} "
          f"two-sided books hold (max error {ident.max_abs_error:.2e})")
    if not ident.holds:
        print("  BROKEN: the complement screen was excluded from Kalshi "
              "because this identity held. Re-derive it before reporting "
              "any Kalshi complement number.", file=sys.stderr)
        for e in ident.examples:
            print(f"    {e}", file=sys.stderr)
    else:
        print("  so YES ask + NO ask = 1 + spread by construction: the "
              "complement screen cannot fire on Kalshi and is not run there.")

    print("\n[complement] venues where the screen can fire")
    poly = complement_mod.screen_polymarket(snap.polymarket)
    print(f"  Polymarket: {poly.pairs:,} quoted outcome pairs "
          f"({poly.two_sided_books:,} two-sided books, {poly.crossed_books} "
          f"crossed), median pair sum "
          f"{poly.overround_median if poly.overround_median is not None else float('nan'):.4f}")
    print(f"    {poly.gross} sum below $1 gross, {poly.net} net of fee")
    if poly.worst:
        w = poly.worst
        print(f"    worst: {w.question[:70]!r} {w.prices} = {w.total:.4f} "
              f"({c(w.gross_edge)} gross, {c(w.net_edge)} net)")
    pi = complement_mod.screen_predictit(snap.predictit)
    print(f"  PredictIt: {pi.pairs:,} YES/NO ask pairs, median cost "
          f"{pi.overround_median if pi.overround_median is not None else float('nan'):.4f}")
    print(f"    {pi.gross} below $1 gross, {pi.net} net of the 10%-of-profit "
          f"and 5%-withdrawal fees")
    if pi.worst:
        w = pi.worst
        print(f"    worst: {w.market_name[:50]!r} / {w.contract_name[:30]!r} "
              f"{w.yes_cost:.2f}+{w.no_cost:.2f} "
              f"({c(w.gross_edge)} gross, {c(w.net_edge)} net)")

    print("\n[bucket sums] mutually exclusive Kalshi events")
    buc = buckets_mod.screen_buckets(snap.kalshi)
    med = buc.median_ask_sum
    print(f"  {buc.screened:,} of {buc.events:,} events with 3+ fully quoted "
          f"buckets, median sum of asks "
          f"{med if med is not None else float('nan'):.3f} "
          f"(above 1 = the normal overround)")
    print(f"  {buc.gross} candidate underrounds gross, {buc.net} net of fees")
    for cand in buc.candidates[:5]:
        print(f"    {cand.event_ticker}: {cand.buckets} buckets, asks sum "
              f"{cand.ask_sum:.3f}, {c(cand.gross_edge)} gross / "
              f"{c(cand.net_edge)} net -- {cand.title[:60]}")
    if buc.candidates:
        print(f"  {buckets_mod.OPEN_UNIVERSE_CAVEAT}")

    print("\n[ladders] Kalshi threshold ladders")
    lad = ladders_mod.screen_ladders(snap.kalshi)
    print(f"  {lad.ladders:,} ladders with 3+ quoted rungs ({lad.rungs:,} "
          f"rungs; {lad.ladders_structured:,} from the venue's strike fields, "
          f"{lad.ladders_title:,} parsed from titles)")
    print(f"  {lad.adjacent_pairs:,} adjacent strike pairs tested")
    print(f"  {lad.inversions_gross} monotonicity inversions gross, "
          f"{lad.inversions_net} net of fee")
    if lad.worst_inversion:
        i = lad.worst_inversion
        print(f"    worst: {i.event_ticker} strike {i.lower_threshold:g} ask "
              f"{i.lower_ask:.2f} vs strike {i.upper_threshold:g} bid "
              f"{i.upper_bid:.2f} -- {c(i.gross_edge)} gross, {c(i.fee)} fee, "
              f"{c(i.net_edge)} net")
    print(f"  {lad.negative_mass_gross} adjacent pairs with negative implied "
          f"mass at mids ({lad.negative_mass_net} beyond two legs of fee, "
          f"total {lad.negative_mass_total:.3f} of probability)")
    fams = ", ".join(f"{k} {v}" for k, v in
                     sorted(lad.by_family.items(), key=lambda kv: -kv[1])[:8])
    if fams:
        print(f"  ladder families: {fams}")

    print(f"\nfee models as of {fees_mod.FEES_AS_OF}:")
    for m in fees_mod.FEE_MODELS.values():
        print(f"  {m.venue}: {m.note}")
        for cav in m.caveats:
            print(f"    caveat: {cav}")
    print("\nNOTE: a coherence measurement, not a trading signal. One "
          "snapshot is an anecdote; the answer is the time series over the "
          "whole archive: python -m pmlab.replay")
    return 0 if ident.holds else 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("snapshot", nargs="?",
                    help="path to a snapshot; default is the newest one")
    ap.add_argument("--archive", default="archive",
                    help="data-branch checkout to include when searching")
    a = ap.parse_args(argv)
    if a.snapshot:
        return report(Path(a.snapshot))
    paths = snapshot_paths(ROOT / "data", Path(a.archive) / "data")
    if not paths:
        print("no snapshots recorded yet; run record.py", file=sys.stderr)
        return 1
    return report(paths[-1])


if __name__ == "__main__":
    sys.exit(main())
