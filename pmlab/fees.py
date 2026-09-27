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
* **Polymarket taker fee** is ``C * rate * (P * (1 - P)) ** exponent``,
  rounded to 5 decimal places with a smallest charge of $0.00001; makers
  pay nothing. Each market's rate and exponent sit in the ``feeSchedule``
  object of its Gamma record, next to ``feesEnabled``. The recorder keeps
  both on every Polymarket row, and a row that carries them is charged
  its own schedule. A row without them is charged the schedule captured
  verbatim in ``docs/polymarket-market-fees-2026-09-27.json``, which
  holds every market behind a complement violation in the archive. A
  market in neither is charged the highest rate in the category table
  Polymarket publishes (0.04 to 0.07, geopolitics 0), so a violation
  counted net of fee survives every rate in that table. Fees have covered
  every category but geopolitics since 2026-03-30, before the archive
  opens, so no quote in it is fee-free by default.
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
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------

#: The day a constant below was last read from its source.
FEES_AS_OF = date(2026, 9, 27)

SOURCES: dict[str, str] = {
    "kalshi": "Kalshi public API, GET /trade-api/v2/series/fee_changes"
              "?show_historical=true on external-api.kalshi.com, read "
              "2026-09-16 and captured verbatim in "
              "docs/kalshi-series-fee-changes-2026-09-16.json. The general "
              "taker formula is quoted in the public API docs; the relative "
              "multiplier's arithmetic is pinned by Kalshi's own fee-halving "
              "announcement (news.kalshi.com/p/were-halving-the-fees, 1.75c "
              "to 0.875c per contract at the midpoint). The rates come from "
              "that feed because the fee-schedule PDF answers HTTP 429 from "
              "this machine.",
    "polymarket": "Polymarket docs, docs.polymarket.com/trading/fees, read "
                  "2026-09-27: taker fee = C x feeRate x p x (1 - p), "
                  "rounded to 5 decimal places, nothing charged to makers, "
                  "category rates from 0.04 to 0.07 and 0 for geopolitics. "
                  "The changelog (docs.polymarket.com/changelog) dates fees "
                  "on every category but geopolitics to 2026-03-30 and says "
                  "fees are computed from each market's feeSchedule object. "
                  "Per-market schedules "
                  "come from the public Gamma API, GET "
                  "gamma-api.polymarket.com/markets/{id}, recorded on every "
                  "row by record.py and captured verbatim for the archive's "
                  "complement violations in "
                  "docs/polymarket-market-fees-2026-09-27.json.",
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
#: Every Kalshi quote sits on a grid no finer than a tenth of a cent and
#: every Kalshi fee is an exact number of cents, so a Kalshi edge is a
#: multiple of 0.001 dollars in exact arithmetic. Polymarket's quoted
#: prices are short decimals too, and its fees are multiples of $0.00001
#: (see :func:`polymarket_taker_fee`). Binary floating point
#: disagrees: ``0.92 - 0.90`` is ``0.020000000000000018``, which is 1.7e-17
#: *more* than the two cents the two legs cost, and an exactly break-even
#: inversion was counted as one that survived the fee. Nine decimals is
#: four orders of magnitude finer than the finest of those grids and eight
#: coarser than the noise, so snapping there deletes the artefact and moves
#: no real number.
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

#: From this date Polymarket charges takers on every category but
#: geopolitics (docs.polymarket.com/changelog, "Fee Structure V2"). The
#: archive opens on 2026-08-23, so no quote in it is fee-free by default.
POLYMARKET_FEES_ALL_CATEGORIES_FROM = date(2026, 3, 30)

#: Taker rates by market category as docs.polymarket.com/trading/fees lists
#: them on 2026-09-27. They are not what a market is charged: each market
#: carries its own feeSchedule, and one category can hold several (the
#: snapshot of 2026-09-27T04:58Z has sports markets on sports_fees_v2 at
#: 0.03 and on sports_fees_v3 at 0.05). The table sets the fallback below.
POLYMARKET_CATEGORY_TAKER_RATES: dict[str, Decimal] = {
    "crypto": Decimal("0.07"),
    "sports": Decimal("0.05"),
    "economics": Decimal("0.05"),
    "culture": Decimal("0.05"),
    "weather": Decimal("0.05"),
    "other": Decimal("0.05"),
    "finance": Decimal("0.04"),
    "politics": Decimal("0.04"),
    "tech": Decimal("0.04"),
    "mentions": Decimal("0.04"),
    "geopolitics": Decimal("0"),
}

#: The rate charged on a market with no recorded and no captured schedule.
#: No snapshot stores a market's category, so it is unknown there, and the
#: highest rate in the table is charged: a violation that survives it
#: survives every rate the table lists.
POLYMARKET_FALLBACK_TAKER_RATE: Decimal = max(
    POLYMARKET_CATEGORY_TAKER_RATES.values())

#: The exponent of the published formula ``rate * P * (1 - P)``, and the one
#: every captured schedule carries.
POLYMARKET_DEFAULT_EXPONENT = 1

#: Polymarket rounds a fee to 5 decimal places and charges at least this.
POLYMARKET_FEE_QUANTUM = Decimal("0.00001")

#: The Gamma records the table below is generated from, written by
#: scripts/capture_polymarket_fees.py.
POLYMARKET_FEE_CAPTURE = "docs/polymarket-market-fees-2026-09-27.json"

#: Taker schedules of individual markets, {conditionId: (rate, exponent)},
#: for rows recorded without ``feeSchedule``. Generated from the Gamma
#: records in :data:`POLYMARKET_FEE_CAPTURE`, never typed: the test
#: ``test_polymarket_schedule_table_matches_the_capture`` re-derives this
#: dict from that file and fails if the two disagree. A market whose record
#: says ``feesEnabled: false`` is stored at rate 0. The comment on each
#: line is the Gamma market id and its ``feeType``.
#:
#: The capture was read on 2026-09-27 and is applied flat to the archive,
#: as the Kalshi table is. A market whose schedule changed between its
#: quote and the read would be charged the later one.
POLYMARKET_MARKET_SCHEDULES: dict[str, tuple[Decimal, int]] = {
    "0x201f51d2d892c41c5bfa6568a0a2f93ab2ea426e87dddfd5fb0191f7ec34a441":
        (Decimal("0.07"), 1),  # 701539 crypto_fees_v2
    "0x2cb1542b43dfdb5b2dc6794a4b97cf6c69099993734917cc9752dfbae4e23680":
        (Decimal("0.04"), 1),  # 3519632 politics_fees
    "0x52327dcfb52af6bd2ea701fd7e7e6e79ed29a1429c2a96d9c6b433871ab37f47":
        (Decimal("0.05"), 1),  # 3529600 sports_fees_v3
    "0x6a7ec981c9882135feafca676b19a2cbcee6e444d9209a58013f110b9f29d75e":
        (Decimal("0.05"), 1),  # 3530815 sports_fees_v3
    "0xf9e3cd3fd2979b296ce3d95f3123959bad7b6b71de5d092197c5e63351ef6134":
        (Decimal("0.05"), 1),  # 3557912 sports_fees_v3
    "0x230accd93377e95dc6caec7ee49265c587bcf80cedad321b90eab36da4d9b366":
        (Decimal("0.05"), 1),  # 3586021 sports_fees_v3
    "0xa49daddd701498d273c8fd516a9ab9a019e0b4914ce26be50743100eaf290bad":
        (Decimal("0.05"), 1),  # 3593466 sports_fees_v3
    "0x7a954fcd55c5fc1a811a50c5b9b60ce66613a185b9b680a371d2f9b2f45f1f88":
        (Decimal("0.05"), 1),  # 3597573 sports_fees_v3
    "0xcdea2bdfbf5fd3f77fd789e398aac82e488ee576b0dc8a03ecbecdafa40d79ee":
        (Decimal("0.05"), 1),  # 3600008 sports_fees_v3
    "0x0a79efee940f8178beb8b75a9db1d3fb1cd957cafc17712091e563277f7ed7a3":
        (Decimal("0.05"), 1),  # 3630744 sports_fees_v3
    "0x492744dc0d172a0b5e51e5f01d44a18b886e31c137daf7fb41c520c290de9c61":
        (Decimal("0.05"), 1),  # 3636176 sports_fees_v3
    "0x8d19053b73744d1d06d977b0911374e3b8442be27edfb6bcd1781cf0e828320a":
        (Decimal("0.05"), 1),  # 3656898 sports_fees_v3
    "0x472ce591e13fe0409a6ded16f39c85f11ad8c1361c04d8b725da35bf02c24df1":
        (Decimal("0.05"), 1),  # 3666417 sports_fees_v3
    "0xfb3f391ef907b93bb7b5932b55e2910c50aff28b7bb9fca707f59cf708c1e4da":
        (Decimal("0.05"), 1),  # 3667806 sports_fees_v3
    "0xef9fdd833811f57b696b558edfab71a2eba1211ef626a29d63dd42967af17965":
        (Decimal("0.05"), 1),  # 3691920 sports_fees_v3
    "0xe8e6059ecfe3998a5b6b64bfa4d284fa8d7e8693167297318a41373a02d73e72":
        (Decimal("0.05"), 1),  # 3743844 sports_fees_v3
    "0x51404a0dbd7fa53009da1888d947d082b08c19bd296f958cf15e74a2e64524ed":
        (Decimal("0.05"), 1),  # 3746632 sports_fees_v3
    "0x97a46f73ef77127f63f804f4a6b5fc06ab8460e8ce2888efa02bfe2fe9d88d5a":
        (Decimal("0.05"), 1),  # 3754109 sports_fees_v3
    "0xa1a6222e0e5cdbab8a60206bd6f996acb335f57a77a01df6651cc0fed90642a8":
        (Decimal("0.05"), 1),  # 3755115 sports_fees_v3
    "0x341dd7476ae4c589298c1c453f3366a8ec58e22e1578a0948cd2317b0147f5b2":
        (Decimal("0.05"), 1),  # 3758232 sports_fees_v3
    "0x77707e31961fc34136cc5b163cec8430a1770224733ed23e757d952e2ee11e2d":
        (Decimal("0.04"), 1),  # 3768581 mentions_fees
    "0x2112581bfa654141f749db62f07b3287ea4c0fa287484936f67e535a94e5a2f4":
        (Decimal("0.05"), 1),  # 3782109 sports_fees_v3
    "0x72d2d4bf1476725a4b4696af61ab26aea531c922829eb2656b579a9a6ea5527b":
        (Decimal("0.05"), 1),  # 3783058 sports_fees_v3
    "0x5c3046522f7b1793a4f7f28d6d682fe978f6f537e858c2fabe1fb5d86b583511":
        (Decimal("0.05"), 1),  # 3785948 sports_fees_v3
    "0xfe8653736500a605086650df4c9dbc01b621ccd477e7dc14549e3c0114e348ad":
        (Decimal("0.05"), 1),  # 3787278 sports_fees_v3
    "0xadc036ea20d58bba37e2e3fe6351f4d87da1dac26baac38d21397735fbfc3c1f":
        (Decimal("0.05"), 1),  # 3795578 sports_fees_v3
    "0x6759e78ff301ddd06126b0ca99e73d44246ee53ba8936c2fd6ec1a144fdf8c30":
        (Decimal("0.05"), 1),  # 3797142 sports_fees_v3
    "0x236593e85012a08c0885c8ad8a2b86156752a7faba39fb2fabf77167d23046b1":
        (Decimal("0.05"), 1),  # 3802520 sports_fees_v3
    "0x370f1f6f98b2f170da7ef0c3dd708116723488c4562a1018c3697248dcbf1d42":
        (Decimal("0.05"), 1),  # 3809276 sports_fees_v3
    "0x1b03c42d5e2b29d3aa40a3dba5fca0fbd4b9b2aaa35619aa357218d41b21ccef":
        (Decimal("0.05"), 1),  # 3840571 sports_fees_v3
    "0xc4cc7781c31a2b2d2af249f9140c808ba3c48f3c40e45b3b7b3ea9974a2abdf1":
        (Decimal("0.05"), 1),  # 3849202 sports_fees_v3
    "0x5861465514ab97f15cc6593184e1f8fdb8358623207088210a49d7f7c43dba2f":
        (Decimal("0.05"), 1),  # 3877412 sports_fees_v3
    "0x482a74551e21d519f37c210c7a81c9165a81e124a30e96e38906514f59c6cdf8":
        (Decimal("0.04"), 1),  # 3887682 finance_prices_fees
    "0x946be491084a28d0052fd4aa94aea890d5162ef5832917c643551acd4185cc71":
        (Decimal("0.05"), 1),  # 3972821 sports_fees_v3
    "0xdc5f8127fd4c33a8395d7abf960a69fad6702628fadf6dd21637e2840c8b32a0":
        (Decimal("0.05"), 1),  # 4004404 sports_fees_v3
    "0x3c04313caade0dc007d7baeb34b8b83edb044a0ec9f8c4ebfb22f8d6b261b018":
        (Decimal("0.05"), 1),  # 4273431 sports_fees_v3
}


def _as_exponent(x) -> int | Decimal:
    d = Decimal(str(x))
    return int(d) if d == d.to_integral_value() else d


def _recorded_schedule(row: dict) -> tuple[Decimal, int | Decimal] | None:
    """The schedule a snapshot row carries, if record.py kept one."""
    if row.get("feesEnabled") is False:
        return Decimal(0), POLYMARKET_DEFAULT_EXPONENT
    fs = row.get("feeSchedule")
    if not isinstance(fs, dict) or fs.get("rate") is None:
        return None
    return (Decimal(str(fs["rate"])),
            _as_exponent(fs.get("exponent", POLYMARKET_DEFAULT_EXPONENT)))


def polymarket_schedule(market_id: str | None = None,
                        row: dict | None = None
                        ) -> tuple[Decimal, int | Decimal]:
    """(rate, exponent) for one market.

    In order: the schedule recorded on the snapshot ``row``; the captured
    schedule for the row's ``conditionId`` or ``id``, or for ``market_id``;
    the fallback rate with exponent 1.
    """
    keys: list[str] = []
    if row is not None:
        rec = _recorded_schedule(row)
        if rec is not None:
            return rec
        keys += [str(row[k]) for k in ("conditionId", "id") if row.get(k)]
    if market_id:
        keys.append(str(market_id))
    for k in keys:
        s = POLYMARKET_MARKET_SCHEDULES.get(k)
        if s is not None:
            return s
    return POLYMARKET_FALLBACK_TAKER_RATE, POLYMARKET_DEFAULT_EXPONENT


def polymarket_taker_fee(price: float, size: float = 1.0,
                         market_id: str | None = None,
                         row: dict | None = None) -> float:
    """Taker fee in dollars for ``size`` shares bought at ``price``.

    ``size * rate * (P * (1 - P)) ** exponent``, rounded half-up to 5
    decimal places with a floor of $0.00001 on any non-zero charge. The
    rounding is Polymarket's, not Kalshi's cent ceiling: at a rate of 0.05
    one share at 0.98 costs $0.00098, where a cent ceiling would charge
    ten times that. A price of 0 or 1 costs nothing.

    >>> polymarket_taker_fee(0.50, row={"feeSchedule": {"rate": 0.05, "exponent": 1}})
    0.0125
    >>> polymarket_taker_fee(0.98, row={"feeSchedule": {"rate": 0.05, "exponent": 1}})
    0.00098
    """
    if size <= 0:
        return 0.0
    p = Decimal(str(price))
    if p <= 0 or p >= 1:
        return 0.0
    rate, exponent = polymarket_schedule(market_id, row)
    if rate <= 0:
        return 0.0
    raw = Decimal(str(size)) * rate * (p * (Decimal(1) - p)) ** exponent
    fee = raw.quantize(POLYMARKET_FEE_QUANTUM, rounding=ROUND_HALF_UP)
    return float(max(fee, POLYMARKET_FEE_QUANTUM))


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
                 "answers HTTP 429 from here; only quadratic (taker) rows "
                 "are used, so a series known only through a "
                 "market-maker-program row stays on the general 0.07",
                 "the table holds the rate in force on 2026-09-16 and is "
                 "flat in time; every series it changes for this archive "
                 "changed before the window opened, so the replay is exact, "
                 "but a mid-window change would need a dated lookup",),
    ),
    "polymarket": VenueFees(
        venue="polymarket",
        note="taker fee = C * rate * (P * (1-P)) ** exponent per order, "
             "rounded to 5 decimal places, minimum $0.00001; rate and "
             "exponent from the market's own Gamma feeSchedule",
        source=SOURCES["polymarket"],
        caveats=("a row recorded without feeSchedule is charged the "
                 f"schedule captured in {POLYMARKET_FEE_CAPTURE} for every "
                 "market behind a complement violation in the archive, "
                 "applied flat in time",
                 "a market with neither a recorded nor a captured schedule "
                 f"is charged {POLYMARKET_FALLBACK_TAKER_RATE}, the highest "
                 "category rate, because no snapshot stores a market's "
                 "category",),
    ),
    "predictit": VenueFees(
        venue="predictit",
        note="10% of profit on the winning leg, plus 5% on withdrawal",
        source=SOURCES["predictit"],
        caveats=("the profit fee is charged per winning position, so a "
                 "complement pair is quoted at its worst case",),
    ),
}
