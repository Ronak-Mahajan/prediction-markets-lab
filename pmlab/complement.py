"""Complement screens, run only where they can actually fire.

Buying both sides of a binary market must cost at least $1, because the
pair pays exactly $1 whichever way it settles. That is the simplest
coherence rule there is, and on one of the four venues in this archive it
is not a rule at all.

**Kalshi is excluded on purpose.** The venue's NO quotes are the mirror
image of the YES book: ``no_ask == 1 - yes_bid`` on every two-sided book
in every snapshot recorded so far. So YES ask + NO ask == 1 + spread by
construction, and "zero complement violations on Kalshi" measures the
venue's data model, not its prices. The old README reported that tautology
as a first result. Here the identity is asserted instead: if it ever
breaks, the replay fails and the deviation is reported as a broken
invariant, because the honest response to "the data model changed" is to
re-derive the screen, not to publish the first number that falls out.

**Polymarket** is screened on its quoted outcome pair. What the recorder
stores per market is one token's top of book (``bestBid``/``bestAsk``)
plus ``outcomePrices``, the venue's quoted price for *each* outcome. The
strict two-legged ask screen -- YES ask plus NO ask -- is therefore not
computable from this archive, because the complementary token's ask was
never recorded; assuming ``no_ask == 1 - yes_bid`` would import exactly
the tautology that disqualifies Kalshi. What is computable, and is a real
statement about the venue's own numbers, is whether the quoted outcome
prices sum to $1. A pair summing below $1 is an incoherent quote (and, if
the prices are executable, an underround); above $1 is the ordinary
overround. Reported as a quote-coherence count, never as an executable
edge, and the recorder gap is named in the output so nobody mistakes one
for the other. The crossed-book count (``bestBid > bestAsk``) rides along
as a separate data-quality line.

**PredictIt** is the venue where the screen is real. Each contract quotes
``bestBuyYesCost`` and ``bestBuyNoCost`` from two independent books, so
their sum is the honest cost of a guaranteed dollar. Net of fee is where
it gets interesting: PredictIt takes 10% of the profit on the winning leg
and 5% on withdrawal, which is a far heavier charge than a few cents of
spread, so the gross and net counts here are allowed to differ a lot.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .fees import (polymarket_taker_fee, predictit_pair_net_edge,
                   predictit_profit_fee)

TOL = 1e-9


class BrokenInvariant(RuntimeError):
    """The venue's data model changed under a screen that assumed it."""


# --------------------------------------------------------------------------
# Kalshi: an invariant, not a result
# --------------------------------------------------------------------------

@dataclass
class KalshiIdentity:
    checked: int = 0
    deviations: int = 0
    max_abs_error: float = 0.0
    examples: list[dict] = field(default_factory=list)

    @property
    def holds(self) -> bool:
        return self.deviations == 0

    def as_dict(self) -> dict:
        return {"checked": self.checked, "deviations": self.deviations,
                "max_abs_error": round(self.max_abs_error, 9),
                "examples": self.examples[:5], "holds": self.holds}


def kalshi_identity(rows: list[dict], tol: float = 1e-6) -> KalshiIdentity:
    """``no_ask == 1 - yes_bid`` over every two-sided Kalshi book.

    Returns the count and the worst deviation. The caller decides whether
    a deviation is fatal; :func:`assert_kalshi_identity` says it is.
    """
    out = KalshiIdentity()
    for r in rows:
        yb, na = r.get("yes_bid"), r.get("no_ask")
        if yb is None or na is None or not r.get("two_sided"):
            continue
        out.checked += 1
        err = abs((1.0 - yb) - na)
        out.max_abs_error = max(out.max_abs_error, err)
        if err > tol:
            out.deviations += 1
            if len(out.examples) < 5:
                out.examples.append({"ticker": r.get("ticker"),
                                     "yes_bid": yb, "no_ask": na,
                                     "error": round(err, 6)})
    return out


def assert_kalshi_identity(rows: list[dict], where: str = "",
                           tol: float = 1e-6) -> KalshiIdentity:
    """Fail loudly rather than publish a complement number for Kalshi."""
    ident = kalshi_identity(rows, tol=tol)
    if not ident.holds:
        raise BrokenInvariant(
            f"Kalshi no_ask == 1 - yes_bid failed on {ident.deviations} of "
            f"{ident.checked} two-sided books{' in ' + where if where else ''}"
            f" (max error {ident.max_abs_error:.6f}); examples: "
            f"{ident.examples}. The complement screen was excluded from "
            f"Kalshi *because* this identity held. If it no longer holds, "
            f"re-derive the screen before reporting any Kalshi complement "
            f"result.")
    return ident


# --------------------------------------------------------------------------
# Polymarket
# --------------------------------------------------------------------------

#: Outcome pairs that are genuinely complementary two-outcome markets.
COMPLEMENTARY_PAIRS = {("yes", "no"), ("over", "under"), ("up", "down")}


@dataclass(frozen=True)
class PolyViolation:
    market_id: str
    question: str
    outcomes: tuple[str, str]
    prices: tuple[float, float]
    total: float
    gross_edge: float
    net_edge: float
    fee: float
    liquidity: float | None
    era: str


@dataclass
class PolyReport:
    rows: int = 0
    pairs: int = 0                 # two complementary outcomes, both priced
    two_sided_books: int = 0       # bestBid and bestAsk both quoted
    crossed_books: int = 0         # bestBid > bestAsk
    gross: int = 0
    net: int = 0
    overround_median: float | None = None
    worst: PolyViolation | None = None
    violations: list[PolyViolation] = field(default_factory=list)

    def as_dict(self) -> dict:
        def v(x: PolyViolation | None) -> dict | None:
            return None if x is None else {
                "market_id": x.market_id, "question": x.question[:140],
                "outcomes": list(x.outcomes), "prices": list(x.prices),
                "total": round(x.total, 6),
                "gross_edge": round(x.gross_edge, 6),
                "net_edge": round(x.net_edge, 6), "fee": round(x.fee, 6),
                "liquidity": x.liquidity, "era": x.era}

        return {"rows": self.rows, "pairs": self.pairs,
                "two_sided_books": self.two_sided_books,
                "crossed_books": self.crossed_books,
                "gross": self.gross, "net": self.net,
                "overround_median": (None if self.overround_median is None
                                     else round(self.overround_median, 6)),
                "worst": v(self.worst)}


def _outcome_pair(row: dict) -> tuple[tuple[str, str], tuple[float, float]] | None:
    oc = row.get("outcomes")
    if isinstance(oc, str):
        try:
            oc = json.loads(oc)
        except ValueError:
            return None
    pr = row.get("outcomePrices")
    if isinstance(pr, str):
        try:
            pr = json.loads(pr)
        except ValueError:
            return None
    if not oc or not pr or len(oc) != 2 or len(pr) != 2:
        return None
    try:
        a, b = float(pr[0]), float(pr[1])
    except (TypeError, ValueError):
        return None
    names = (str(oc[0]), str(oc[1]))
    if tuple(n.lower() for n in names) not in COMPLEMENTARY_PAIRS:
        return None
    if not (0.0 < a < 1.0 and 0.0 < b < 1.0):
        return None
    return names, (a, b)


def screen_polymarket(rows: list[dict]) -> PolyReport:
    """Quoted outcome pairs that do not sum to $1, gross and net of fee."""
    rep = PolyReport(rows=len(rows))
    totals: list[float] = []
    for r in rows:
        bb, ba = r.get("bestBid"), r.get("bestAsk")
        if bb is not None and ba is not None and bb > 0 and ba > 0:
            rep.two_sided_books += 1
            if bb > ba + TOL:
                rep.crossed_books += 1
        pair = _outcome_pair(r)
        if pair is None:
            continue
        names, (a, b) = pair
        rep.pairs += 1
        total = a + b
        totals.append(total)
        if total >= 1.0 - TOL:
            continue
        mid = str(r.get("conditionId") or r.get("id") or "")
        fee = (polymarket_taker_fee(a, 1.0, mid)
               + polymarket_taker_fee(b, 1.0, mid))
        v = PolyViolation(market_id=str(r.get("id") or ""),
                          question=str(r.get("question") or ""),
                          outcomes=names, prices=(a, b), total=total,
                          gross_edge=1.0 - total,
                          net_edge=1.0 - total - fee, fee=fee,
                          liquidity=r.get("liquidity"),
                          era=str(r.get("era") or ""))
        rep.gross += 1
        if v.net_edge > 0:
            rep.net += 1
        if rep.worst is None or v.gross_edge > rep.worst.gross_edge:
            rep.worst = v
        if len(rep.violations) < 50:
            rep.violations.append(v)
    if totals:
        totals.sort()
        rep.overround_median = totals[len(totals) // 2]
    return rep


# --------------------------------------------------------------------------
# PredictIt
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PiViolation:
    market_id: str
    market_name: str
    contract_id: str
    contract_name: str
    yes_cost: float
    no_cost: float
    gross_edge: float
    net_edge: float


@dataclass
class PiReport:
    contracts: int = 0
    pairs: int = 0
    gross: int = 0
    net: int = 0
    overround_median: float | None = None
    worst: PiViolation | None = None
    violations: list[PiViolation] = field(default_factory=list)

    def as_dict(self) -> dict:
        def v(x: PiViolation | None) -> dict | None:
            return None if x is None else {
                "market_id": x.market_id, "market_name": x.market_name[:140],
                "contract_id": x.contract_id,
                "contract_name": x.contract_name[:80],
                "yes_cost": x.yes_cost, "no_cost": x.no_cost,
                "gross_edge": round(x.gross_edge, 6),
                "net_edge": round(x.net_edge, 6)}

        return {"contracts": self.contracts, "pairs": self.pairs,
                "gross": self.gross, "net": self.net,
                "overround_median": (None if self.overround_median is None
                                     else round(self.overround_median, 6)),
                "worst": v(self.worst)}


def screen_predictit(rows: list[dict], withdraw: bool = True) -> PiReport:
    """YES+NO ask pairs on PredictIt contracts, gross and net of its fees."""
    rep = PiReport(contracts=len(rows))
    totals: list[float] = []
    for r in rows:
        y, n = r.get("bestBuyYesCost"), r.get("bestBuyNoCost")
        if y is None or n is None:
            continue
        if not (0.0 < y < 1.0 and 0.0 < n < 1.0):
            continue
        rep.pairs += 1
        total = y + n
        totals.append(total)
        if total >= 1.0 - TOL:
            continue
        v = PiViolation(market_id=str(r.get("market_id") or ""),
                        market_name=str(r.get("market_name") or ""),
                        contract_id=str(r.get("contract_id") or ""),
                        contract_name=str(r.get("name") or ""),
                        yes_cost=y, no_cost=n, gross_edge=1.0 - total,
                        net_edge=predictit_pair_net_edge(y, n, withdraw))
        rep.gross += 1
        if v.net_edge > 0:
            rep.net += 1
        if rep.worst is None or v.gross_edge > rep.worst.gross_edge:
            rep.worst = v
        if len(rep.violations) < 50:
            rep.violations.append(v)
    if totals:
        totals.sort()
        rep.overround_median = totals[len(totals) // 2]
    return rep


def predictit_breakeven_gross_edge(yes_cost: float, no_cost: float,
                                   withdraw: bool = True) -> float:
    """How much gross edge a PredictIt pair needs before it nets anything.

    Useful in the write-up: at 45c/45c the profit fee alone eats 5.5c, so a
    pair must cost under about 94.5c before the trade exists at all -- an
    order of magnitude more slack than a Kalshi two-cent fee needs.
    """
    worst_leg = min(yes_cost, no_cost)
    proceeds = 1.0 - predictit_profit_fee(worst_leg, 1.0)
    if withdraw:
        proceeds -= 0.05 * proceeds
    return 1.0 - proceeds
