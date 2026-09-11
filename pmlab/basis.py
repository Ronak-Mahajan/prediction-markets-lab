"""Cross-venue basis on hand-curated event pairs.

The same question sometimes trades on two venues. The distance between the
two prices, net of what it costs to trade both sides, is the basis; how
long it survives is the more interesting half.

Why the map is hand-curated
---------------------------

Because automatic matching does not work here, and it was tried before
this file existed. On the first snapshot in the archive, exact title
matching across every venue pair yields **zero** pairs. Token-Jaccard at
0.75 yields **one** pair, and it is wrong: Polymarket's "next cabinet
member to leave" against Kalshi's "first cabinet member to leave" are
different questions with different answers. A keyword overlap between
PredictIt and Kalshi gives 28 candidate pairs out of 187 and the matches
are party-wins markets against margin-of-victory ladders, which do not
settle together.

So :data:`EVENTS_PATH` is written by a person, one pair at a time, under
one rule:

    **Identical entity and identical deadline on both venues.** The two
    markets must resolve YES on exactly the same world-state at exactly
    the same moment, read off both venues' published rules. No fuzzy
    matching, no "close enough", no pair whose deadlines differ by a day.

Every pair carries ``verified: true|false``. A pair is ``verified`` only
once a person has read both venues' rules pages and written down what they
checked. **Unverified pairs are never priced**: they are carried in the
file as a to-do list, counted in the output, and skipped. That is why this
module runs cleanly and reports nothing on a repository whose
``events.yaml`` is a skeleton, which is its state today.

What is measured, for each verified pair
----------------------------------------

* **Mid basis** in cents, ``mid(leg A) - mid(leg B)``, at every snapshot
  where both legs are quoted: median, inter-decile range, and the share of
  snapshots on each side of zero. This is a marking difference, not a
  trade.
* **Executable edge**, net of both venues' fees: buying YES on one venue
  and NO on the other pays exactly $1 whichever way the question resolves,
  so the gross edge of the A->B direction is ``bid_B - ask_A`` and the net
  edge subtracts each leg's own fee with its own rounding. Both directions
  are computed and the better one is reported. A positive net edge is the
  number that would matter; the count of snapshots with one is reported
  next to the distribution, never on its own.
* **Half-life** of the mid basis: an AR(1) through the origin on
  consecutive observations, ``b[i+1] = phi * b[i]``, converted to hours
  with the median spacing of those observations. It is reported only with
  at least :data:`MIN_HALFLIFE_OBS` observations and ``0 < phi < 1``,
  and the median spacing used is reported beside it, because the
  conversion assumes the sampling is roughly regular and the recorder's
  cadence is not perfectly so.

Manifold is not eligible: it is play money, so a dollar basis against it
is not a dollar. A Manifold leg is rejected at load time with that reason.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Sequence

from . import fees as fees_mod
from .archive import Snapshot
from .calibration import _VENUE_KEY, _quote_from_row

#: Where the curated map lives, relative to the repository root.
EVENTS_PATH = "events.yaml"

#: Venues whose prices are denominated in dollars a person can withdraw.
TRADEABLE_VENUES = ("kalshi", "polymarket", "predictit")

#: Below this many joint observations a pair reports its count and nothing
#: else: three quotes are not a distribution.
MIN_OBSERVATIONS = 20

#: Below this many, no half-life is reported at all.
MIN_HALFLIFE_OBS = 20

EMPTY_NOTE = (
    "No verified cross-venue pair is in events.yaml, so there is no basis "
    "to measure. The file ships as a skeleton of examples marked "
    "`verified: false`; pairing is a hand check of both venues' rules "
    "pages (identical entity, identical deadline) and unverified pairs are "
    "counted here and never priced.")

CURATION_RULE = (
    "identical entity and identical deadline on both venues, read off both "
    "rules pages by a person; no fuzzy matching")


# --------------------------------------------------------------------------
# The map
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Leg:
    venue: str
    key: str                    # ticker (Kalshi), id (Polymarket), contract id
    side: str = "yes"           # "yes" or "no": which side this key quotes

    def label(self) -> str:
        return f"{self.venue}:{self.key}" + ("" if self.side == "yes" else " (NO)")


@dataclass(frozen=True)
class Pair:
    id: str
    question: str
    deadline: str
    legs: tuple[Leg, Leg]
    verified: bool = False
    checked_by: str = ""
    checked_on: str = ""
    note: str = ""


@dataclass
class PairFile:
    path: str
    exists: bool = False
    parsed: bool = False
    reason: str = ""
    pairs: list[Pair] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)

    @property
    def verified(self) -> list[Pair]:
        return [p for p in self.pairs if p.verified]


def _side_of(raw) -> str:
    """``side`` as written, with YAML 1.1's booleans put back.

    An unquoted ``side: yes`` in YAML 1.1 is the boolean ``True``, not the
    string "yes", and a curator writing this file by hand will type it
    unquoted sooner or later. Mapping the booleans back is the whole fix;
    the alternative is a rejected pair with a baffling reason.
    """
    if isinstance(raw, bool):
        return "yes" if raw else "no"
    return str(raw if raw is not None else "yes").strip().lower()


def _leg_from(obj: dict) -> tuple[Leg | None, str]:
    venue = str(obj.get("venue", "")).strip().lower()
    key = obj.get("key")
    side = _side_of(obj.get("side", "yes"))
    if venue == "manifold":
        return None, ("manifold is play money, so a dollar basis against it "
                      "is not a dollar")
    if venue not in TRADEABLE_VENUES:
        return None, f"unknown venue {venue!r}"
    if key in (None, ""):
        return None, "leg has no key"
    if side not in ("yes", "no"):
        return None, f"side must be yes or no, not {side!r}"
    return Leg(venue, str(key), side), ""


def load_pairs(path: str | Path = EVENTS_PATH) -> PairFile:
    """Read events.yaml. A missing file or a missing PyYAML is a *state*,
    reported in the output, not an exception."""
    p = Path(path)
    out = PairFile(path=str(p))
    if not p.is_file():
        out.reason = f"{p} does not exist"
        return out
    out.exists = True
    try:
        import yaml                              # noqa: PLC0415
    except ImportError:
        # Said out loud rather than silently degrading: a replay without
        # PyYAML would otherwise report "no pairs" for a file full of them.
        out.reason = ("PyYAML is not installed, so events.yaml was not read "
                      "(pip install -r requirements-analysis.txt)")
        return out
    try:
        with open(p, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
    except Exception as exc:                     # noqa: BLE001 - reported, not raised
        out.reason = f"{p} could not be parsed: {exc!r}"
        return out
    out.parsed = True
    for i, raw in enumerate(doc.get("pairs") or []):
        if not isinstance(raw, dict):
            out.rejected.append({"index": i, "reason": "entry is not a mapping"})
            continue
        legs_raw = raw.get("legs") or []
        pid = str(raw.get("id") or f"pair-{i}")
        if len(legs_raw) != 2:
            out.rejected.append({"id": pid, "reason": "a pair needs exactly two legs"})
            continue
        legs, bad = [], ""
        for lr in legs_raw:
            leg, why = _leg_from(lr if isinstance(lr, dict) else {})
            if leg is None:
                bad = why
                break
            legs.append(leg)
        if bad:
            out.rejected.append({"id": pid, "reason": bad})
            continue
        if legs[0].venue == legs[1].venue:
            out.rejected.append({"id": pid, "reason": "both legs are on the same venue"})
            continue
        verified = bool(raw.get("verified", False))
        if verified and not str(raw.get("checked_on") or "").strip():
            # "verified" with nobody's name and no date on it is a claim,
            # not a check.
            out.rejected.append({"id": pid,
                                 "reason": "verified: true with no checked_on date"})
            continue
        out.pairs.append(Pair(
            id=pid, question=str(raw.get("question") or ""),
            deadline=str(raw.get("deadline") or ""), legs=(legs[0], legs[1]),
            verified=verified, checked_by=str(raw.get("checked_by") or ""),
            checked_on=str(raw.get("checked_on") or ""),
            note=str(raw.get("note") or "")))
    return out


# --------------------------------------------------------------------------
# Pricing one leg
# --------------------------------------------------------------------------

def leg_quote(venue: str, row: dict, side: str) -> tuple[float, float] | None:
    """(bid, ask) for the side this leg is on, or None if not quoted.

    A NO leg is the complement of the recorded YES book: its bid is
    ``1 - yes_ask`` and its ask is ``1 - yes_bid``. That is an identity on
    the order book, not an assumption about the venue.
    """
    q = _quote_from_row(venue, row)
    if q is None:
        return None
    bid, ask = q[0], q[1]
    if side == "no":
        bid, ask = 1.0 - ask, 1.0 - bid
    if bid is None or ask is None:
        return None
    return bid, ask


def leg_fee(venue: str, price: float, key: str | None = None) -> float:
    """Taker fee in dollars for one contract at ``price`` on ``venue``.

    PredictIt does not charge on entry at all; it takes 10% of the profit
    if the position wins and 5% of what is withdrawn. Charging the full
    profit fee plus withdrawal on every leg is therefore an *upper* bound
    on what a PredictIt leg costs, which is the direction a screen should
    err in.
    """
    if venue == "kalshi":
        return fees_mod.kalshi_taker_fee(price, 1)
    if venue == "polymarket":
        return fees_mod.polymarket_taker_fee(price, 1.0, key)
    if venue == "predictit":
        proceeds = 1.0 - fees_mod.predictit_profit_fee(price, 1.0)
        proceeds -= fees_mod.predictit_withdrawal_fee(proceeds)
        return 1.0 - proceeds
    return 0.0


def pair_edges(a: tuple[float, float], b: tuple[float, float],
               leg_a: Leg, leg_b: Leg) -> dict:
    """Gross and net edge for both directions of one cross-venue pair.

    Buying YES on one venue and NO on the other pays exactly $1 however the
    question resolves, so the A->B direction costs ``ask_a + (1 - bid_b)``
    and the gross edge is ``bid_b - ask_a``.
    """
    bid_a, ask_a = a
    bid_b, ask_b = b
    gross_ab = bid_b - ask_a
    net_ab = gross_ab - leg_fee(leg_a.venue, ask_a, leg_a.key) \
        - leg_fee(leg_b.venue, 1.0 - bid_b, leg_b.key)
    gross_ba = bid_a - ask_b
    net_ba = gross_ba - leg_fee(leg_b.venue, ask_b, leg_b.key) \
        - leg_fee(leg_a.venue, 1.0 - bid_a, leg_a.key)
    best = "a->b" if net_ab >= net_ba else "b->a"
    return {"gross_ab": gross_ab, "net_ab": net_ab,
            "gross_ba": gross_ba, "net_ba": net_ba,
            "best_direction": best, "best_net": max(net_ab, net_ba),
            "best_gross": gross_ab if best == "a->b" else gross_ba}


# --------------------------------------------------------------------------
# Half-life
# --------------------------------------------------------------------------

def ar1_half_life(values: Sequence[float],
                  gaps_hours: Sequence[float]) -> dict:
    """Half-life of a mean-reverting series, from an AR(1) through the origin.

    ``phi`` is the least-squares slope of ``b[i+1]`` on ``b[i]``, and the
    half-life is ``ln(0.5) / ln(phi)`` steps converted to hours with the
    median step. Returns the reason instead of a number when the fit does
    not support one -- ``phi >= 1`` is a series that is not reverting and
    ``phi <= 0`` is one that alternates, and neither has a half-life.
    """
    n = len(values)
    out: dict = {"n_steps": max(0, n - 1), "phi": None,
                 "half_life_hours": None, "median_step_hours": None,
                 "reason": ""}
    if n - 1 < MIN_HALFLIFE_OBS:
        out["reason"] = (f"{max(0, n - 1)} steps is fewer than the "
                         f"{MIN_HALFLIFE_OBS} this fit needs")
        return out
    num = sum(values[i] * values[i + 1] for i in range(n - 1))
    den = sum(values[i] * values[i] for i in range(n - 1))
    if den <= 0:
        out["reason"] = "the basis is identically zero"
        return out
    phi = num / den
    out["phi"] = phi
    step = statistics.median(gaps_hours) if gaps_hours else None
    out["median_step_hours"] = step
    if phi <= 0:
        out["reason"] = f"phi={phi:.4f} <= 0: the series alternates, no half-life"
        return out
    if phi >= 1:
        out["reason"] = f"phi={phi:.4f} >= 1: not mean-reverting over this window"
        return out
    if not step:
        out["reason"] = "no usable spacing between observations"
        return out
    out["half_life_hours"] = math.log(0.5) / math.log(phi) * step
    return out


# --------------------------------------------------------------------------
# The join
# --------------------------------------------------------------------------

class BasisJoin:
    """Collect both legs of every verified pair across the archive."""

    def __init__(self, pairfile: PairFile):
        self.pairfile = pairfile
        self.pairs = pairfile.verified
        self.snapshots_seen = 0
        #: {pair id: [(t, (bid_a, ask_a), (bid_b, ask_b))]}
        self._series: dict[str, list[tuple[datetime, tuple, tuple]]] = {
            p.id: [] for p in self.pairs}
        #: {pair id: [legs seen at all]} - a pair whose key is simply not in
        #: the catalog is a curation error, and saying so is the point.
        self._leg_seen: dict[str, set[str]] = {p.id: set() for p in self.pairs}

    def observe(self, snap: Snapshot) -> None:
        self.snapshots_seen += 1
        if not self.pairs:
            return
        index: dict[str, dict[str, dict]] = {}
        wanted: dict[str, set[str]] = {}
        for p in self.pairs:
            for leg in p.legs:
                wanted.setdefault(leg.venue, set()).add(leg.key)
        for venue, keys in wanted.items():
            kf = _VENUE_KEY[venue]
            index[venue] = {}
            for r in snap.venues.get(venue, []):
                k = r.get(kf)
                if k is not None and str(k) in keys:
                    index[venue][str(k)] = r
        for p in self.pairs:
            qs = []
            for leg in p.legs:
                row = index.get(leg.venue, {}).get(leg.key)
                if row is None:
                    qs.append(None)
                    continue
                self._leg_seen[p.id].add(leg.label())
                qs.append(leg_quote(leg.venue, row, leg.side))
            if qs[0] is not None and qs[1] is not None:
                self._series[p.id].append((snap.t, qs[0], qs[1]))

    def report(self) -> dict:
        pf = self.pairfile
        rep: dict = {
            "events_file": pf.path,
            "events_file_exists": pf.exists,
            "events_file_parsed": pf.parsed,
            "events_file_reason": pf.reason,
            "curation_rule": CURATION_RULE,
            "pairs_total": len(pf.pairs),
            "pairs_verified": len(pf.verified),
            "pairs_unverified": len(pf.pairs) - len(pf.verified),
            "pairs_rejected": pf.rejected,
            "snapshots_seen": self.snapshots_seen,
            "min_observations": MIN_OBSERVATIONS,
            "empty": not pf.verified,
            "note": "" if pf.verified else EMPTY_NOTE,
            "pairs": [],
            "unverified_ids": [p.id for p in pf.pairs if not p.verified],
        }
        for p in self.pairs:
            series = sorted(self._series[p.id], key=lambda x: x[0])
            row: dict = {
                "id": p.id, "question": p.question, "deadline": p.deadline,
                "legs": [leg.label() for leg in p.legs],
                "checked_by": p.checked_by, "checked_on": p.checked_on,
                "observations": len(series),
                "legs_ever_quoted": sorted(self._leg_seen[p.id]),
            }
            if len(series) < MIN_OBSERVATIONS:
                row["reason"] = (
                    f"{len(series)} joint observations is fewer than the "
                    f"{MIN_OBSERVATIONS} needed for a distribution"
                    + ("" if self._leg_seen[p.id] else
                       "; neither leg was found in any snapshot, which is a "
                       "curation error, not a market fact"))
                rep["pairs"].append(row)
                continue
            mids_a = [(q[0] + q[1]) / 2.0 for _, q, _ in series]
            mids_b = [(q[0] + q[1]) / 2.0 for _, _, q in series]
            basis = [(a - b) * 100.0 for a, b in zip(mids_a, mids_b)]
            edges = [pair_edges(qa, qb, p.legs[0], p.legs[1])
                     for _, qa, qb in series]
            nets = [e["best_net"] * 100.0 for e in edges]
            gross = [e["best_gross"] * 100.0 for e in edges]
            gaps = [(series[i + 1][0] - series[i][0]).total_seconds() / 3600.0
                    for i in range(len(series) - 1)]
            row.update({
                "first": series[0][0].strftime("%Y-%m-%dT%H:%M:%SZ"),
                "last": series[-1][0].strftime("%Y-%m-%dT%H:%M:%SZ"),
                "basis_cents": {
                    "median": round(statistics.median(basis), 3),
                    "mean": round(statistics.fmean(basis), 3),
                    "p10": round(_pct(basis, 0.10), 3),
                    "p90": round(_pct(basis, 0.90), 3),
                    "abs_median": round(statistics.median(
                        [abs(x) for x in basis]), 3),
                    "share_positive": round(
                        sum(1 for x in basis if x > 0) / len(basis), 4),
                },
                "edge_cents": {
                    "gross_median": round(statistics.median(gross), 3),
                    "gross_max": round(max(gross), 3),
                    "net_median": round(statistics.median(nets), 3),
                    "net_max": round(max(nets), 3),
                    "snapshots_net_positive": sum(1 for x in nets if x > 0),
                },
                "half_life": ar1_half_life(basis, gaps),
            })
            rep["pairs"].append(row)
        return rep


def _pct(xs: list[float], q: float) -> float:
    s = sorted(xs)
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[i]


def empty_report(path: str | Path = EVENTS_PATH) -> dict:
    """The report shape with nothing to price (a missing file included)."""
    return BasisJoin(load_pairs(path)).report()
