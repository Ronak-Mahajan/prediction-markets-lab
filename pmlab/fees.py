"""Dated per-venue fee constants, with the rounding each venue actually uses.

A screen that reports "gross violations" and stops is a screen that has not
been run. Every count in this package is produced twice: gross, and net of
the fee the venue charges to put the trade on. The whole point of the
exercise is the gap between the two, so the fee model has to be the real
one rather than a convenient approximation.

What is pinned here, and what is deliberately not:

* **Kalshi taker fee** is the published formula, with the published
  rounding: ``ceil_to_cent(multiplier * C * P * (1 - P))`` where ``C`` is
  the contract count and ``P`` the price in dollars. The rounding is per
  *order*, and the smallest non-zero fee is therefore one cent: a single
  contract at 1c costs 0.07 * 0.01 * 0.99 = $0.000693 of fee and is
  charged $0.01. That floor is the single most important number in this
  file. It is why a one-cent gross ladder inversion is not a trade: two
  legs cost two cents of fee against one cent of edge.
  ``screen.py`` used to charge the unrounded ``0.07 * p * (1 - p)``
  (0.0007 on that contract, 14x too little), so "survives the fee model"
  was permissive by more than an order of magnitude at the tails.
* **Kalshi reduced multipliers.** Some series are priced below the general
  rate. The table below is filled from Kalshi's own public, unauthenticated
  ``GET /trade-api/v2/series/fee_changes?show_historical=true``, captured
  verbatim in ``docs/kalshi-series-fee-changes-2026-09-16.json``. That feed
  reports a multiplier *relative* to the general rate: 1 is the general
  0.07, 0.5 is half, 0 is no fee at all. Kalshi's own announcement of the
  S&P and Nasdaq change pins the arithmetic -- 1.75c to 0.875c per contract
  at the midpoint, which is 0.07 * 0.25 halved to 0.035 * 0.25 -- so what is
  stored here is 0.07 times the relative multiplier. Only rows whose
  ``fee_type`` is one of the quadratic (taker) kinds are used;
  ``margin_market_maker_program_fees`` rows describe a different charge, so
  a series known only through one of those stays on the general rate.
  The fee-schedule PDF is still unread from this machine: it sits behind a
  bot checkpoint and answers HTTP 429.
* **Polymarket** charges no taker fee on the central limit order book by
  default. That default is a real fact about the venue, not a shortcut,
  but it has been changed per-market before, so the constant is a lookup
  with an override map rather than a literal zero at the call site.
* **PredictIt** charges 10% of the *profit* on a position that wins (not
  of the notional, and nothing at all on a loser) plus 5% on withdrawal
  of funds from the site. A complement pair pays the profit fee on
  whichever leg wins, so the fee-honest proceeds of the pair are set by
  the *worst* case, i.e. the cheaper leg winning.

Every constant carries the date it was read and the source it was read
from. When a venue changes its schedule the old entry stays and a new
dated entry is added, because a replay of the 2026 archive must be
charged the 2026 fees.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_CEILING, Decimal

# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------

#: The day every constant below was last read from its source.
FEES_AS_OF = date(2026, 9, 11)

SOURCES: dict[str, str] = {
    "kalshi": "Kalshi public API, GET /trade-api/v2/series/fee_changes"
              "?show_historical=true on external-api.kalshi.com, read "
              "2026-09-16 and captured verbatim in "
              "docs/kalshi-series-fee-changes-2026-09-16.json. The general "
              "taker formula is quoted in the public API docs; the relative "
              "multiplier's arithmetic is pinned by Kalshi's own fee-halving "
              "announcement (news.kalshi.com/p/were-halving-the-fees, 1.75c "
              "-> 0.875c per contract at the midpoint). The fee-schedule PDF "
              "itself has NOT been read on this machine (HTTP 429).",
    "polymarket": "Polymarket docs: CLOB trading currently charges no taker "
                  "or maker fee; the protocol supports per-market fees.",
    "predictit": "PredictIt FAQ: 10% of profit on a winning position, 5% of "
                 "funds withdrawn from the site.",
}


# --------------------------------------------------------------------------
# Kalshi
# --------------------------------------------------------------------------

#: General taker multiplier in ``ceil_to_cent(m * C * P * (1 - P))``.
KALSHI_TAKER_MULTIPLIER = Decimal("0.07")

#: Maker fees are zero on the series this archive covers. Kept as a named
#: constant so a future dated schedule has somewhere to land.
KALSHI_MAKER_MULTIPLIER = Decimal("0.00")

#: Absolute taker multipliers for the series Kalshi prices below the general
#: rate, i.e. 0.07 times the relative multiplier its fee_changes feed reports.
#: Generated from the captured response, never typed: the test
#: ``test_reduced_multiplier_table_matches_the_captured_feed`` re-derives this
#: dict from docs/kalshi-series-fee-changes-2026-09-16.json and fails if the
#: two disagree.
#:
#: This table is flat in time while the feed is dated. Every entry that
#: touches the committed archive took effect before the window opened -- the
#: latest relevant one is KXGDPYEAR on 2026-07-28, and the window starts
#: 2026-08-23 -- so a flat lookup is exact for this replay. A series whose
#: rate moved mid-window would need a dated lookup, and none does.
KALSHI_REDUCED_TAKER_MULTIPLIER: dict[str, Decimal] = {
    "KXBCHPERP": Decimal("0"),          # 2026-06-03, x0
    "KXBTCPERP": Decimal("0"),          # 2026-06-03, x0
    "KXBTCY": Decimal("0"),             # 2026-02-26, x0
    "KXCITRINI": Decimal("0"),          # 2026-02-26, x0
    "KXDOED": Decimal("0"),             # 2025-10-21, x0
    "KXDOGEPERP": Decimal("0"),         # 2026-06-03, x0
    "KXDOTPERP": Decimal("0"),          # 2026-06-03, x0
    "KXELECTIRAN": Decimal("0"),        # 2026-03-03, x0
    "KXETHPERP": Decimal("0"),          # 2026-06-03, x0
    "KXETHY": Decimal("0"),             # 2026-02-26, x0
    "KXEXPAND": Decimal("0"),           # 2025-10-21, x0
    "KXGAMBLINGREPEAL": Decimal("0"),   # 2025-10-21, x0
    "KXGDPYEAR": Decimal("0"),          # 2026-07-28, x0
    "KXGREENLAND": Decimal("0"),        # 2025-10-21, x0
    "KXHBARPERP": Decimal("0"),         # 2026-06-03, x0
    "KXHYPEPERP": Decimal("0"),         # 2026-06-08, x0
    "KXIRANDEMOCRACY": Decimal("0"),    # 2026-03-03, x0
    "KXKSHIBPERP": Decimal("0"),        # 2026-06-03, x0
    "KXLAYOFFSYINFO": Decimal("0"),     # 2026-02-26, x0
    "KXLINKPERP": Decimal("0"),         # 2026-06-03, x0
    "KXLTCPERP": Decimal("0"),          # 2026-06-03, x0
    "KXMLBEXTRAS": Decimal("0.035"),    # 2026-08-07, x0.5
    "KXMLBF3": Decimal("0.035"),        # 2026-08-07, x0.5
    "KXMLBF5": Decimal("0.035"),        # 2026-08-07, x0.5
    "KXMLBF5SPREAD": Decimal("0.035"),  # 2026-08-07, x0.5
    "KXMLBF5TOTAL": Decimal("0.035"),   # 2026-08-07, x0.5
    "KXMLBF7": Decimal("0.035"),        # 2026-08-07, x0.5
    "KXMLBGAME": Decimal("0.035"),      # 2026-08-07, x0.5
    "KXMLBHIT": Decimal("0.035"),       # 2026-08-07, x0.5
    "KXMLBHR": Decimal("0.035"),        # 2026-08-07, x0.5
    "KXMLBHRR": Decimal("0.035"),       # 2026-08-07, x0.5
    "KXMLBKS": Decimal("0.035"),        # 2026-08-07, x0.5
    "KXMLBOUTS": Decimal("0.035"),      # 2026-08-07, x0.5
    "KXMLBRBI": Decimal("0.035"),       # 2026-08-07, x0.5
    "KXMLBRFI": Decimal("0.035"),       # 2026-08-07, x0.5
    "KXMLBSB": Decimal("0.035"),        # 2026-08-07, x0.5
    "KXMLBSPREAD": Decimal("0.035"),    # 2026-08-07, x0.5
    "KXMLBTB": Decimal("0.035"),        # 2026-08-07, x0.5
    "KXMLBTEAMTOTAL": Decimal("0.035"), # 2026-08-07, x0.5
    "KXMLBTOTAL": Decimal("0.035"),     # 2026-08-07, x0.5
    "KXNEARPERP": Decimal("0"),         # 2026-06-24, x0
    "KXNEXTIRANLEADER": Decimal("0"),   # 2026-03-03, x0
    "KXPAHLAVIHEAD": Decimal("0"),      # 2026-03-03, x0
    "KXSOLPERP": Decimal("0"),          # 2026-06-03, x0
    "KXSUIPERP": Decimal("0"),          # 2026-06-03, x0
    "KXTRUMPOUT": Decimal("0"),         # 2025-10-21, x0
    "KXXLMPERP": Decimal("0"),          # 2026-06-03, x0
    "KXXRPPERP": Decimal("0"),          # 2026-06-03, x0
    "KXZECPERP": Decimal("0"),          # 2026-06-24, x0
}

_CENT = Decimal("0.01")

#: Decimal places an edge is snapped to before it is compared with a fee.
#:
#: Every quote in this archive sits on a grid no finer than a tenth of a
#: cent and every fee above is an exact number of cents, so an edge is a
#: multiple of 0.001 dollars in exact arithmetic. Binary floating point
#: disagrees: ``0.92 - 0.90`` is ``0.020000000000000018``, which is 1.7e-17
#: *more* than the two cents the two legs cost, and an exactly break-even
#: inversion was counted as one that survived the fee. Nine decimals is six
#: orders of magnitude finer than the grid and eight coarser than the noise,
#: so snapping there deletes the artefact and moves no real number.
EDGE_DIGITS = 9


def edge(x: float) -> float:
    """A dollar edge, snapped back onto the grid the venue quotes on."""
    return round(x, EDGE_DIGITS)


def survives(net_edge: float) -> bool:
    """Is this edge positive on the quoting grid, rather than in float noise?"""
    return edge(net_edge) > 0.0


def ceil_to_cent(x: Decimal) -> Decimal:
    """Round a dollar amount UP to the next whole cent, as the venue does."""
    return x.quantize(_CENT, rounding=ROUND_CEILING)


def kalshi_taker_multiplier(series_ticker: str | None = None) -> Decimal:
    """The multiplier for one series: the reduced one if the table lists it,
    otherwise the general one."""
    if series_ticker:
        m = KALSHI_REDUCED_TAKER_MULTIPLIER.get(series_ticker.upper())
        if m is not None:
            return m
    return KALSHI_TAKER_MULTIPLIER


def kalshi_taker_fee(price: float, contracts: int = 1,
                     series_ticker: str | None = None) -> float:
    """Taker fee in dollars for ``contracts`` at ``price`` dollars each.

    ``ceil_to_cent(multiplier * C * P * (1 - P))``. A price of exactly 0 or
    1 (or outside [0, 1], which the loader can produce from a missing
    quote) costs nothing, because there is no risk to charge for.

    >>> kalshi_taker_fee(0.50)          # 0.07 * 0.25 = 0.0175 -> 2c
    0.02
    >>> kalshi_taker_fee(0.01)          # 0.000693 -> the one-cent floor
    0.01
    >>> kalshi_taker_fee(0.50, 100)     # 1.75 exactly, no rounding up
    1.75
    """
    if contracts <= 0:
        return 0.0
    p = Decimal(str(price))
    if p <= 0 or p >= 1:
        return 0.0
    m = kalshi_taker_multiplier(series_ticker)
    raw = m * Decimal(contracts) * p * (Decimal(1) - p)
    return float(ceil_to_cent(raw))


def kalshi_pair_fee(price_a: float, price_b: float, contracts: int = 1,
                    series_ticker: str | None = None) -> float:
    """Fee for the two legs of a spread, rounded per leg as the venue bills.

    Two separate orders means two separate ceilings, which is why a 1c
    gross edge across two legs is never a 1c net edge.
    """
    return (kalshi_taker_fee(price_a, contracts, series_ticker)
            + kalshi_taker_fee(price_b, contracts, series_ticker))


# --------------------------------------------------------------------------
# Polymarket
# --------------------------------------------------------------------------

#: Default taker fee rate on the CLOB: none.
POLYMARKET_DEFAULT_TAKER_RATE = 0.0

#: {condition_id or market id: taker rate as a fraction of notional}. Empty
#: because no market in this archive is known to charge one; the override
#: exists so a future fee shows up in every net number without a code change.
POLYMARKET_TAKER_OVERRIDES: dict[str, float] = {}


def polymarket_taker_rate(market_id: str | None = None) -> float:
    if market_id is not None:
        r = POLYMARKET_TAKER_OVERRIDES.get(str(market_id))
        if r is not None:
            return r
    return POLYMARKET_DEFAULT_TAKER_RATE


def polymarket_taker_fee(price: float, size: float = 1.0,
                         market_id: str | None = None) -> float:
    """Fee in dollars for ``size`` shares at ``price``.

    Zero for every market in this archive, and the replay says so out loud
    rather than quietly reporting gross numbers as net ones.
    """
    rate = polymarket_taker_rate(market_id)
    if rate <= 0:
        return 0.0
    return float(ceil_to_cent(Decimal(str(rate)) * Decimal(str(size))
                              * Decimal(str(price))))


# --------------------------------------------------------------------------
# PredictIt
# --------------------------------------------------------------------------

PREDICTIT_PROFIT_FEE_RATE = 0.10      # of profit, on a winning position only
PREDICTIT_WITHDRAWAL_FEE_RATE = 0.05  # of funds withdrawn from the site


def predictit_profit_fee(cost: float, payout: float = 1.0) -> float:
    """10% of the profit on a winning contract; nothing on a loser."""
    profit = payout - cost
    if profit <= 0:
        return 0.0
    return PREDICTIT_PROFIT_FEE_RATE * profit


def predictit_withdrawal_fee(amount: float) -> float:
    """5% of whatever leaves the site. Charged once, on the way out."""
    return PREDICTIT_WITHDRAWAL_FEE_RATE * max(0.0, amount)


def predictit_pair_net_edge(yes_cost: float, no_cost: float,
                            withdraw: bool = True) -> float:
    """Net edge in dollars on buying one YES and one NO of the same contract.

    The pair pays $1 whichever way the contract settles, so the gross edge
    is ``1 - yes - no``. Exactly one leg wins, and PredictIt takes 10% of
    *that leg's* profit, so the worst case -- the one a screen must quote --
    is the cheaper leg winning and paying the larger profit fee. With
    ``withdraw``, 5% of the dollar that comes back is charged too, which is
    what it costs to actually hold the money.

    >>> round(predictit_pair_net_edge(0.45, 0.45, withdraw=False), 4)
    0.045
    """
    worst_leg_cost = min(yes_cost, no_cost)          # largest profit -> largest fee
    proceeds = 1.0 - predictit_profit_fee(worst_leg_cost, 1.0)
    if withdraw:
        proceeds -= predictit_withdrawal_fee(proceeds)
    return proceeds - (yes_cost + no_cost)


@dataclass(frozen=True)
class VenueFees:
    """What the replay prints next to every net number, so a reader knows
    which model produced it without opening this file."""

    venue: str
    as_of: date = FEES_AS_OF
    note: str = ""
    source: str = ""
    caveats: tuple[str, ...] = field(default_factory=tuple)


FEE_MODELS: dict[str, VenueFees] = {
    "kalshi": VenueFees(
        venue="kalshi",
        note="taker fee = ceil to the cent of 0.07 * contracts * P * (1-P), "
             "per order; minimum one cent per order with any risk",
        source=SOURCES["kalshi"],
        caveats=("the per-series multipliers come from Kalshi's public "
                 "fee_changes feed rather than the fee-schedule PDF, which "
                 "is still unreadable from here; only quadratic (taker) rows "
                 "are used, so a series known only through a "
                 "market-maker-program row stays on the general 0.07",
                 "the table holds the rate in force on 2026-09-16 and is "
                 "flat in time; every series it changes for this archive "
                 "changed before the window opened, so the replay is exact, "
                 "but a mid-window change would need a dated lookup",),
    ),
    "polymarket": VenueFees(
        venue="polymarket",
        note="no taker fee on the CLOB; per-market overrides supported",
        source=SOURCES["polymarket"],
        caveats=("with a zero fee the net numbers equal the gross ones by "
                 "construction; they are reported separately anyway so the "
                 "day a fee appears the table changes on its own",),
    ),
    "predictit": VenueFees(
        venue="predictit",
        note="10% of profit on the winning leg, plus 5% on withdrawal",
        source=SOURCES["predictit"],
        caveats=("the profit fee is charged per winning position, so a "
                 "complement pair is quoted at its worst case",),
    ),
}
