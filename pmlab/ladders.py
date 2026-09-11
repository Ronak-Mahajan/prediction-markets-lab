"""Threshold ladders: group the rungs, imply P(>= s), test the shape.

A Kalshi threshold event lists one market per strike on the same
underlying variable ("above 4.25%", "above 4.50%", ...). Together the
rungs are a quoted survival function, and a survival function has rules:
it must not increase with the strike, and the mass it implies between
adjacent strikes must not be negative. Those rules need no model, only
arithmetic, which is what makes them worth measuring on real quotes.

Two ways to find the rungs, because the archive has two schemas:

* **structured** (recorder v2): the venue's own ``strike_type`` plus
  ``floor_strike`` / ``cap_strike``. Authoritative -- the strike is a
  number the exchange published, not a number parsed out of English.
* **title** (recorder v1, 2026-08-23 to the v2 merge): the strike lives
  only in ``yes_sub_title``. The old ``screen.py`` regex matched two
  shapes and so found 44 ladders on the first snapshot out of a catalog
  that actually carries hundreds; the families below cover the shapes
  that appear in this archive, counted by frequency, not guessed.

Normalisation. Every rung is reduced to ``P(X >= threshold)`` with a
bid/ask interval:

* ``greater`` / ``greater_or_equal`` rungs (and every "Above N" title
  family) are already P(>= s).
* ``less`` / ``less_or_equal`` rungs quote P(X <= cap). The complement
  P(X >= cap) is ``[1 - ask, 1 - bid]`` -- the interval flips, and so do
  the sides. The Kalshi fee is symmetric in P <-> 1-P, so a flipped leg
  costs exactly what the unflipped one would; no fee correction is needed.
* ``between`` rungs are buckets, not ladder rungs, and are handled by
  :mod:`pmlab.buckets`.

The two screens, each gross and net:

**Monotonicity inversion** (at the touch, executable). For adjacent
strikes ``s1 < s2``: P(>= s2) must not exceed P(>= s1). A violation that
a trade could take is ``bid(s2) > ask(s1)`` -- sell the higher strike at
its bid, buy the lower at its ask, and collect the difference whatever
happens, because the higher strike can never settle YES while the lower
settles NO. Gross edge is ``bid(s2) - ask(s1)``; the net edge subtracts
the venue fee on *both* legs, each rounded up to the cent on its own.
A one-cent gross inversion therefore nets to minus one cent, which is the
single most common way this class of screen lies.

**Butterfly / negative implied mass** (at the mid, informational). The
mass the ladder implies between adjacent strikes is
``mid(s1) - mid(s2)``; negative mass means the quoted curve bends the
wrong way. Measured at mids it is a statement about where the market is
marked rather than about a trade, so it is reported gross, and "net" is
the stricter question of whether the negative mass exceeds the fee on the
two legs it would take to collect it.

Nothing here is a trading signal. It is a count of how often quoted
probability curves are shaped impossibly, and how much of that survives
the venue's own fee schedule.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .fees import kalshi_taker_fee

# --------------------------------------------------------------------------
# Title families (recorder v1)
# --------------------------------------------------------------------------

_NUM = r"([\d][\d,]*(?:\.\d+)?)"

#: (family name, compiled regex, multiplier, unit class). ``unit`` decides
#: which rungs may share a ladder: a "5%" strike and a "5 million" strike
#: are not two rungs of one curve even inside one event.
TITLE_FAMILIES: tuple[tuple[str, re.Pattern[str], float, str], ...] = (
    # "Above 220K", "Above 2.6M", "Above 189 thousand", "Above 405 million"
    ("above_k", re.compile(rf"^above\s+\$?{_NUM}\s*k$", re.I), 1e3, "scalar"),
    ("above_m", re.compile(rf"^above\s+\$?{_NUM}\s*m$", re.I), 1e6, "scalar"),
    ("above_thousand", re.compile(rf"^above\s+\$?{_NUM}\s+thousand$", re.I),
     1e3, "scalar"),
    ("above_million", re.compile(rf"^above\s+\$?{_NUM}\s+million$", re.I),
     1e6, "scalar"),
    ("above_billion", re.compile(rf"^above\s+\$?{_NUM}\s+billion$", re.I),
     1e9, "scalar"),
    # "Above 0.5%", "At least 60%"
    ("above_pct", re.compile(rf"^above\s+{_NUM}\s*%$", re.I), 1.0, "percent"),
    ("at_least_pct", re.compile(rf"^at\s+least\s+{_NUM}\s*%$", re.I),
     1.0, "percent"),
    ("pct_or_above", re.compile(
        rf"^{_NUM}\s*%\s+or\s+(?:above|higher|more)$", re.I), 1.0, "percent"),
    # "Above $25.00", "Above 800"
    ("above_plain", re.compile(rf"^above\s+\$?{_NUM}$", re.I), 1.0, "scalar"),
    ("at_least", re.compile(rf"^at\s+least\s+\$?{_NUM}$", re.I), 1.0, "scalar"),
    # "10,600.0001 or above", "36 or more", "At or above 55"
    ("or_above", re.compile(
        rf"^\$?{_NUM}\s+or\s+(?:above|higher|more)$", re.I), 1.0, "scalar"),
    ("at_or_above", re.compile(
        rf"^at\s+or\s+above\s+\$?{_NUM}$", re.I), 1.0, "scalar"),
)

#: "Republicans, 26+ pts" / "Democrats, 4+ pts": a margin-of-victory ladder
#: whose rungs are only comparable within one party, so the party joins the
#: ladder key instead of being thrown away.
PARTY_MARGIN = re.compile(rf"^(?P<party>[A-Za-z][A-Za-z ]*?),?\s+{_NUM}\+\s*pts$",
                          re.I)

#: A bare "36+ pts" with no party named.
PLAIN_PLUS_PTS = re.compile(rf"^{_NUM}\+\s*pts$", re.I)


def parse_title_threshold(sub_title: str) -> tuple[float, str, str] | None:
    """``yes_sub_title`` -> (threshold, family, unit) or None.

    >>> parse_title_threshold("Above 220K")
    (220000.0, 'above_k', 'scalar')
    >>> parse_title_threshold("Republicans, 26+ pts")
    (26.0, 'party_margin', 'margin:republicans')
    >>> parse_title_threshold("Before Jan 1, 2030") is None
    True
    """
    s = (sub_title or "").strip()
    if not s:
        return None
    for name, rx, mult, unit in TITLE_FAMILIES:
        m = rx.match(s)
        if m:
            return float(m.group(1).replace(",", "")) * mult, name, unit
    m = PARTY_MARGIN.match(s)
    if m:
        party = m.group("party").strip().lower()
        return (float(m.group(2).replace(",", "")), "party_margin",
                f"margin:{party}")
    m = PLAIN_PLUS_PTS.match(s)
    if m:
        return float(m.group(1).replace(",", "")), "plus_pts", "margin:?"
    return None


# --------------------------------------------------------------------------
# Rungs and ladders
# --------------------------------------------------------------------------

GE_STRIKES = {"greater", "greater_or_equal"}
LE_STRIKES = {"less", "less_or_equal"}


@dataclass(frozen=True)
class Rung:
    """One market, normalised to a quote on ``P(X >= threshold)``."""

    ticker: str
    threshold: float
    bid: float                 # highest price someone will pay for P(>= s)
    ask: float                 # lowest price someone will sell P(>= s) at
    flipped: bool = False      # built from a "less" market by complement

    @property
    def mid(self) -> float:
        return 0.5 * (self.bid + self.ask)


@dataclass
class Ladder:
    """Rungs of one event that quote the same variable in the same unit.

    The grouping key is ``(event_ticker, unit, source)``. For structured
    rungs ``unit`` is the venue's ``strike_type``, so a "greater" ladder and
    a "less" ladder on the same event stay apart exactly as the spec asks.
    For title-parsed rungs ``unit`` is the unit *class* -- scalar, percent,
    or margin-in-points-for-one-party -- rather than the regex that matched,
    so an event that writes "Above 900K" and "Above 1M" on the same curve
    still yields one ladder while a percent strike never joins a dollar one.
    """

    event_ticker: str
    series_ticker: str | None
    unit: str
    source: str                # "strike" | "title"
    rungs: list[Rung] = field(default_factory=list)
    families: dict[str, int] = field(default_factory=dict)

    @property
    def family(self) -> str:
        """The title family (or strike type) most of the rungs came from."""
        if not self.families:
            return self.unit
        return max(sorted(self.families), key=lambda k: self.families[k])

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.event_ticker, self.unit, self.source)


@dataclass(frozen=True)
class Inversion:
    """A higher strike bid over a lower strike's ask: shape, not noise."""

    event_ticker: str
    lower_ticker: str
    upper_ticker: str
    lower_threshold: float
    upper_threshold: float
    lower_ask: float
    upper_bid: float
    gross_edge: float
    net_edge: float
    fee: float


@dataclass(frozen=True)
class NegativeMass:
    """Negative implied PMF between adjacent strikes, measured at mids."""

    event_ticker: str
    lower_ticker: str
    upper_ticker: str
    lower_threshold: float
    upper_threshold: float
    mass: float                # negative
    fee: float                 # cost of the two legs that would collect it


def _quote(row: dict) -> tuple[float, float] | None:
    b, a = row.get("yes_bid"), row.get("yes_ask")
    if b is None or a is None:
        return None
    if not (0.0 < b <= a < 1.0):
        return None
    return float(b), float(a)


def _structured_rung(row: dict) -> tuple[float, str, bool] | None:
    """(threshold, unit, flipped) from the venue's own strike fields."""
    st = (row.get("strike_type") or "").strip().lower()
    if st in GE_STRIKES:
        v = row.get("floor_strike")
        if v is None:
            return None
        return float(v), "strike:" + st, False
    if st in LE_STRIKES:
        v = row.get("cap_strike")
        if v is None:
            return None
        return float(v), "strike:" + st, True
    return None


def build_ladders(rows: list[dict], min_rungs: int = 3) -> list[Ladder]:
    """Group Kalshi market rows into threshold ladders.

    Structured strike fields win wherever the recorder captured them; the
    title parser fills in for the v1 snapshots, which is most of this
    archive. A market never lands in two ladders: the structured path is
    tried first and the title path only sees what it did not claim.
    """
    groups: dict[tuple, Ladder] = {}
    for row in rows:
        q = _quote(row)
        if q is None:
            continue
        bid, ask = q
        ev = row.get("event_ticker")
        if not ev:
            continue
        s = _structured_rung(row)
        if s is not None:
            threshold, unit, flipped = s
            source, family = "strike", unit
        else:
            t = parse_title_threshold(row.get("yes_sub_title") or "")
            if t is None:
                continue
            threshold, family, unit = t
            source, flipped = "title", False
        if flipped:                        # P(>= cap) = 1 - P(<= cap)
            bid, ask = 1.0 - ask, 1.0 - bid
        key = (ev, unit, source)
        lad = groups.get(key)
        if lad is None:
            lad = groups[key] = Ladder(event_ticker=ev,
                                       series_ticker=row.get("series_ticker"),
                                       unit=unit, source=source)
        lad.families[family] = lad.families.get(family, 0) + 1
        lad.rungs.append(Rung(ticker=row.get("ticker") or "",
                              threshold=threshold, bid=bid, ask=ask,
                              flipped=flipped))
    out: list[Ladder] = []
    for lad in groups.values():
        # One strike quoted twice is a data problem, not two rungs: keep the
        # first and let the ladder stand, rather than dropping the event.
        seen: set[float] = set()
        rungs = []
        for r in sorted(lad.rungs, key=lambda r: r.threshold):
            if r.threshold in seen:
                continue
            seen.add(r.threshold)
            rungs.append(r)
        lad.rungs = rungs
        if len(rungs) >= min_rungs:
            out.append(lad)
    out.sort(key=lambda lad: lad.key)
    return out


# --------------------------------------------------------------------------
# Screens
# --------------------------------------------------------------------------

def ladder_inversions(lad: Ladder, series_ticker: str | None = None
                      ) -> list[Inversion]:
    """Beyond-spread monotonicity violations on one ladder, gross and net."""
    st = series_ticker if series_ticker is not None else lad.series_ticker
    out: list[Inversion] = []
    for lo, hi in zip(lad.rungs, lad.rungs[1:]):
        gross = hi.bid - lo.ask
        if gross <= 0:
            continue
        fee = kalshi_taker_fee(lo.ask, 1, st) + kalshi_taker_fee(hi.bid, 1, st)
        out.append(Inversion(event_ticker=lad.event_ticker,
                             lower_ticker=lo.ticker, upper_ticker=hi.ticker,
                             lower_threshold=lo.threshold,
                             upper_threshold=hi.threshold,
                             lower_ask=lo.ask, upper_bid=hi.bid,
                             gross_edge=gross, net_edge=gross - fee, fee=fee))
    return out


def ladder_negative_mass(lad: Ladder, series_ticker: str | None = None
                         ) -> list[NegativeMass]:
    """Adjacent strikes whose implied mass at mids is negative."""
    st = series_ticker if series_ticker is not None else lad.series_ticker
    out: list[NegativeMass] = []
    for lo, hi in zip(lad.rungs, lad.rungs[1:]):
        mass = lo.mid - hi.mid
        if mass >= 0:
            continue
        fee = kalshi_taker_fee(lo.mid, 1, st) + kalshi_taker_fee(hi.mid, 1, st)
        out.append(NegativeMass(event_ticker=lad.event_ticker,
                                lower_ticker=lo.ticker, upper_ticker=hi.ticker,
                                lower_threshold=lo.threshold,
                                upper_threshold=hi.threshold,
                                mass=mass, fee=fee))
    return out


def implied_pmf(lad: Ladder) -> list[tuple[float, float, float]]:
    """[(lower strike, upper strike, implied mass at mids)] for one ladder.

    The last bucket -- everything at or above the top strike -- is the top
    rung's own mid, and the first -- everything below the bottom strike --
    is ``1 - mid(bottom)``. Both are included so the list sums to 1 and a
    reader can see immediately where a negative entry sits in the curve.
    """
    if not lad.rungs:
        return []
    out: list[tuple[float, float, float]] = [
        (float("-inf"), lad.rungs[0].threshold, 1.0 - lad.rungs[0].mid)]
    for lo, hi in zip(lad.rungs, lad.rungs[1:]):
        out.append((lo.threshold, hi.threshold, lo.mid - hi.mid))
    out.append((lad.rungs[-1].threshold, float("inf"), lad.rungs[-1].mid))
    return out


@dataclass
class LadderReport:
    ladders: int = 0
    rungs: int = 0
    ladders_structured: int = 0
    ladders_title: int = 0
    adjacent_pairs: int = 0
    inversions_gross: int = 0
    inversions_net: int = 0
    negative_mass_gross: int = 0
    negative_mass_net: int = 0
    negative_mass_total: float = 0.0
    worst_inversion: Inversion | None = None
    worst_net_inversion: Inversion | None = None
    worst_negative_mass: NegativeMass | None = None
    by_family: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        def inv(i: Inversion | None) -> dict | None:
            return None if i is None else {
                "event_ticker": i.event_ticker,
                "lower_ticker": i.lower_ticker, "upper_ticker": i.upper_ticker,
                "lower_threshold": i.lower_threshold,
                "upper_threshold": i.upper_threshold,
                "lower_ask": i.lower_ask, "upper_bid": i.upper_bid,
                "gross_edge": round(i.gross_edge, 6),
                "net_edge": round(i.net_edge, 6), "fee": round(i.fee, 6)}

        def nm(n: NegativeMass | None) -> dict | None:
            return None if n is None else {
                "event_ticker": n.event_ticker,
                "lower_ticker": n.lower_ticker, "upper_ticker": n.upper_ticker,
                "lower_threshold": n.lower_threshold,
                "upper_threshold": n.upper_threshold,
                "mass": round(n.mass, 6), "fee": round(n.fee, 6)}

        return {
            "ladders": self.ladders, "rungs": self.rungs,
            "ladders_structured": self.ladders_structured,
            "ladders_title": self.ladders_title,
            "adjacent_pairs": self.adjacent_pairs,
            "inversions_gross": self.inversions_gross,
            "inversions_net": self.inversions_net,
            "negative_mass_gross": self.negative_mass_gross,
            "negative_mass_net": self.negative_mass_net,
            "negative_mass_total": round(self.negative_mass_total, 6),
            "worst_inversion": inv(self.worst_inversion),
            "worst_net_inversion": inv(self.worst_net_inversion),
            "worst_negative_mass": nm(self.worst_negative_mass),
            "by_family": dict(sorted(self.by_family.items())),
        }


def screen_ladders(rows: list[dict], min_rungs: int = 3) -> LadderReport:
    """Every ladder in one snapshot's Kalshi rows, screened gross and net."""
    rep = LadderReport()
    for lad in build_ladders(rows, min_rungs=min_rungs):
        rep.ladders += 1
        rep.rungs += len(lad.rungs)
        rep.adjacent_pairs += max(0, len(lad.rungs) - 1)
        if lad.source == "strike":
            rep.ladders_structured += 1
        else:
            rep.ladders_title += 1
        rep.by_family[lad.family] = rep.by_family.get(lad.family, 0) + 1
        for i in ladder_inversions(lad):
            rep.inversions_gross += 1
            if rep.worst_inversion is None or i.gross_edge > rep.worst_inversion.gross_edge:
                rep.worst_inversion = i
            if i.net_edge > 0:
                rep.inversions_net += 1
                if (rep.worst_net_inversion is None
                        or i.net_edge > rep.worst_net_inversion.net_edge):
                    rep.worst_net_inversion = i
        for n in ladder_negative_mass(lad):
            rep.negative_mass_gross += 1
            rep.negative_mass_total += n.mass
            if (rep.worst_negative_mass is None
                    or n.mass < rep.worst_negative_mass.mass):
                rep.worst_negative_mass = n
            if -n.mass > n.fee:
                rep.negative_mass_net += 1
    return rep
