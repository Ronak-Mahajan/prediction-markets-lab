"""Bucket sums on mutually exclusive events, as a time series.

If an event's buckets are mutually exclusive *and exhaustive*, buying one
of each costs at least $1, because exactly one pays. Asks summing below $1
is therefore a candidate underround.

Candidate is the operative word, and the original README was right to
insist on it. ``mutually_exclusive`` is the venue's flag for "at most one
of these settles YES"; it says nothing about whether the listed buckets
cover every outcome. The events that survive this screen on real data are
precisely the ones where they do not -- next pope, 51st state, party
nominations -- because an open-universe event's listed buckets leave out
"someone else", and the missing bucket is exactly the mass that makes the
sum come in under a dollar. So the screen is kept, the caveat travels with
every number it produces, and the output names the surviving events so a
reader can see for themselves what kind of event they are.

Two guards keep the count from being manufactured:

* at least three quoted buckets, so a two-way market is not counted twice
  as the complement screen;
* every bucket must have a live ask. One bucket with no offer makes the
  sum meaningless, and the missing one is usually the favourite, which
  would turn every thin event into a fake underround.

Gross is the sum of asks. Net adds the venue fee on every leg, each
rounded up to the cent on its own, which for a ten-bucket event is ten
separate cents of floor -- the reason a "10c edge" across many legs is
routinely not an edge at all.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .fees import kalshi_taker_fee


@dataclass(frozen=True)
class BucketCandidate:
    event_ticker: str
    series_ticker: str | None
    title: str
    buckets: int
    ask_sum: float
    fee: float
    gross_edge: float
    net_edge: float


@dataclass
class BucketReport:
    events: int = 0                 # mutually exclusive events seen
    screened: int = 0               # with 3+ fully quoted buckets
    median_ask_sum: float | None = None
    gross: int = 0
    net: int = 0
    worst: BucketCandidate | None = None
    candidates: list[BucketCandidate] = field(default_factory=list)

    def as_dict(self) -> dict:
        def c(x: BucketCandidate | None) -> dict | None:
            return None if x is None else {
                "event_ticker": x.event_ticker,
                "series_ticker": x.series_ticker, "title": x.title[:140],
                "buckets": x.buckets, "ask_sum": round(x.ask_sum, 6),
                "fee": round(x.fee, 6),
                "gross_edge": round(x.gross_edge, 6),
                "net_edge": round(x.net_edge, 6)}

        return {"events": self.events, "screened": self.screened,
                "median_ask_sum": (None if self.median_ask_sum is None
                                   else round(self.median_ask_sum, 6)),
                "gross": self.gross, "net": self.net,
                "worst": c(self.worst),
                "top": [c(x) for x in self.candidates[:10]]}


def group_events(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        ev = r.get("event_ticker")
        if not ev:
            continue
        out.setdefault(ev, []).append(r)
    return out


def screen_buckets(rows: list[dict], min_buckets: int = 3) -> BucketReport:
    """Mutually-exclusive bucket sums for one snapshot, gross and net."""
    rep = BucketReport()
    sums: list[float] = []
    for ev, markets in group_events(rows).items():
        if not any(m.get("mutually_exclusive") for m in markets):
            continue
        rep.events += 1
        asks = [m.get("yes_ask") for m in markets]
        if len(asks) < min_buckets:
            continue
        if any(a is None or not 0.0 < a <= 1.0 for a in asks):
            continue
        rep.screened += 1
        s = float(sum(asks))                     # type: ignore[arg-type]
        sums.append(s)
        series = next((m.get("series_ticker") for m in markets
                       if m.get("series_ticker")), None)
        fee = sum(kalshi_taker_fee(float(a), 1, series) for a in asks)  # type: ignore[arg-type]
        if s >= 1.0:
            continue
        cand = BucketCandidate(
            event_ticker=ev, series_ticker=series,
            title=str(next((m.get("event_title") or m.get("title") or ""
                            for m in markets), "")),
            buckets=len(asks), ask_sum=s, fee=fee,
            gross_edge=1.0 - s, net_edge=1.0 - s - fee)
        rep.gross += 1
        if cand.net_edge > 0:
            rep.net += 1
        if rep.worst is None or cand.gross_edge > rep.worst.gross_edge:
            rep.worst = cand
        rep.candidates.append(cand)
    rep.candidates.sort(key=lambda c: -c.gross_edge)
    if sums:
        sums.sort()
        rep.median_ask_sum = sums[len(sums) // 2]
    return rep


OPEN_UNIVERSE_CAVEAT = (
    "A bucket-sum candidate is NOT an arbitrage. The venue's "
    "mutually_exclusive flag promises at most one bucket settles YES, not "
    "that the listed buckets are exhaustive; the survivors on real data are "
    "open-universe events (next pope, 51st state, party nominations) whose "
    "missing 'someone else' bucket is exactly the mass that makes the asks "
    "sum below a dollar. Read the event rules before believing any row of "
    "this table.")
