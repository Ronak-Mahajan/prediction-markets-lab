"""Phase 1 coherence screener: do quoted probabilities obey the rules?

Runs against the newest recorded snapshot (or a given one) and checks the
constraints that need no model at all, only logic:

  1. Complement: on Kalshi, buying YES and NO at the ask must cost at
     least $1; less is a gross arbitrage. Reported gross AND net of the
     venue's trading fee, because the whole lesson of screening real
     markets is that gross violations are usually just the spread.
  2. Bucket sums: for a mutually exclusive Kalshi event, the sum of YES
     asks below $1 is a candidate underround (buy every bucket, one must
     pay). Candidate, not certain: the flag does not promise the buckets
     are exhaustive, so each hit needs a human read of the rules.
  3. Ladder monotonicity: threshold markets on one variable ("X or
     above") must price P(>= s) decreasing in s. Inversions beyond the
     spread are incoherence between strikes.

Every number printed is a count or a distribution over the whole
snapshot; single cherry-picked hits are how this class of tool lies.

    python screen.py                # newest snapshot
    python screen.py data/20260823/0118Z.json.gz
"""
from __future__ import annotations

import gzip
import json
import re
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"

# Kalshi taker fee per contract, both legs of a $1-payout pair:
# ceil-free approximation of 0.07 * p * (1-p), documented by the venue.
def kalshi_fee(p: float) -> float:
    return 0.07 * p * (1.0 - p)


LADDER = re.compile(
    r"(?:^(?:above|at or above)\s+\$?([\d,]+(?:\.\d+)?)\s*$)"
    r"|(?:^\$?([\d,]+(?:\.\d+)?)\s+or\s+(?:above|higher|more)\s*$)",
    re.IGNORECASE)


def load(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def f(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def screen_complement(events: list[dict]) -> None:
    quoted = gross = net = 0
    best = None
    for ev in events:
        for m in ev["markets"]:
            ya, na = f(m.get("yes_ask_dollars")), f(m.get("no_ask_dollars"))
            if not (0 < ya < 1 and 0 < na < 1):
                continue
            quoted += 1
            cost = ya + na
            if cost >= 1.0:
                continue
            gross += 1
            edge = 1.0 - cost - kalshi_fee(ya) - kalshi_fee(na)
            if edge > 0:
                net += 1
                if best is None or edge > best[0]:
                    best = (edge, m.get("ticker"), ya, na)
    print(f"[complement] {quoted} two-sided Kalshi books: "
          f"{gross} gross YES+NO < $1, {net} survive the fee model")
    if best:
        print(f"  best net edge {best[0]*100:.1f}c on {best[1]} "
              f"(yes ask {best[2]:.2f}, no ask {best[3]:.2f})")


def screen_bucket_sums(events: list[dict]) -> None:
    sums, candidates = [], []
    for ev in events:
        if not ev.get("mutually_exclusive"):
            continue
        asks = [f(m.get("yes_ask_dollars")) for m in ev["markets"]]
        # Every bucket must be buyable: one bucket with no ask makes the
        # sum meaningless and manufactures a fake underround (the missing
        # bucket is usually the favorite).
        if len(asks) < 3 or any(not 0 < a <= 1 for a in asks):
            continue
        s = sum(asks)
        sums.append(s)
        fees = sum(kalshi_fee(a) for a in asks)
        if s + fees < 1.0:
            candidates.append((1.0 - s - fees, ev["event_ticker"], len(asks)))
    if sums:
        sums.sort()
        mid = sums[len(sums) // 2]
        print(f"[bucket sums] {len(sums)} mutually-exclusive events with 3+ "
              f"quoted buckets: median sum of asks {mid:.2f} "
              f"(above 1 = the normal overround)")
    candidates.sort(reverse=True)
    print(f"  {len(candidates)} candidate underrounds net of fees "
          f"(exhaustiveness NOT verified; read the event rules)")
    for edge, tick, n in candidates[:5]:
        print(f"    {tick}: {n} buckets, apparent edge {edge*100:.1f}c")


def screen_ladders(events: list[dict]) -> None:
    ladders = inversions = 0
    worst = None
    for ev in events:
        rungs = []
        for m in ev["markets"]:
            g = LADDER.search((m.get("yes_sub_title") or "").strip())
            yb, ya = f(m.get("yes_bid_dollars")), f(m.get("yes_ask_dollars"))
            if g and 0 < yb <= ya < 1:
                strike = (g.group(1) or g.group(2)).replace(",", "")
                rungs.append((float(strike), yb, ya))
        if len(rungs) < 3:
            continue
        rungs.sort()
        ladders += 1
        for (s1, b1, a1), (s2, b2, a2) in zip(rungs, rungs[1:]):
            # P(>= s2) must not exceed P(>= s1): a HIGHER threshold whose
            # BID clears the lower threshold's ASK is beyond-spread
            # incoherence, not noise.
            if b2 > a1:
                inversions += 1
                gap = b2 - a1
                if worst is None or gap > worst[0]:
                    worst = (gap, ev["event_ticker"], s1, s2)
    print(f"[ladders] {ladders} threshold ladders with 3+ quoted rungs: "
          f"{inversions} beyond-spread monotonicity inversions")
    if worst:
        print(f"  worst: {worst[1]} strikes {worst[2]:g} vs {worst[3]:g}, "
              f"bid over ask by {worst[0]*100:.1f}c")


def main() -> None:
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        snaps = sorted(DATA.glob("*/*.json.gz"))
        if not snaps:
            raise SystemExit("no snapshots recorded yet; run record.py")
        path = snaps[-1]
    snap = load(path)
    print(f"snapshot {snap['t']}")
    for name, rows in snap["venues"].items():
        print(f"  {name}: {len(rows)} rows")
    events = snap["venues"].get("kalshi", [])
    if not events:
        raise SystemExit("no kalshi events in this snapshot")
    print()
    screen_complement(events)
    print()
    screen_bucket_sums(events)
    print()
    screen_ladders(events)
    print("\nNOTE: this is a coherence measurement, not a trading signal. "
          "Most gross violations are the spread wearing a costume; the "
          "screen exists to measure how often anything survives honest "
          "fee accounting, snapshot after snapshot.")


if __name__ == "__main__":
    main()
