"""Phase 2 screens: fees, ladders, complement, buckets, replay, drift check.

The fixtures here are hand-built rather than cut from the archive, because
the point of each one is a planted violation whose correct answer was
worked out on paper first. The archive fixtures in ``test_schema.py`` pin
the *shapes* the loader must survive; these pin the *arithmetic*.

The load-bearing case is ``test_planted_inversion_is_erased_by_fees``: a
one-cent gross ladder inversion, which the old unrounded fee model would
have called a surviving edge, and which the venue's actual per-order
ceiling turns into a one-cent loss.
"""
from __future__ import annotations

import gzip
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pmlab import buckets, complement, fees, ladders          # noqa: E402
from pmlab import replay as replay_mod                        # noqa: E402
from pmlab.archive import load_snapshot                       # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------
# helpers: rows in the shape pmlab.archive produces
# --------------------------------------------------------------------------

def kmarket(ticker: str, event: str, bid: float, ask: float, *,
            sub_title: str = "", strike_type: str | None = None,
            floor_strike: float | None = None,
            cap_strike: float | None = None,
            series: str | None = None,
            mutually_exclusive: bool = False,
            title: str = "") -> dict:
    """One coerced Kalshi row, with the NO side built to the venue's identity."""
    return {
        "ticker": ticker, "event_ticker": event, "series_ticker": series,
        "yes_sub_title": sub_title, "title": title, "event_title": title,
        "strike_type": strike_type, "floor_strike": floor_strike,
        "cap_strike": cap_strike, "mutually_exclusive": mutually_exclusive,
        "yes_bid": bid, "yes_ask": ask,
        "no_bid": round(1.0 - ask, 10), "no_ask": round(1.0 - bid, 10),
        "two_sided": bid > 0 and ask > 0, "quoted": True,
    }


def poly_row(mid: str, question: str, yes: float, no: float,
             bid: float = 0.0, ask: float = 0.0,
             outcomes=("Yes", "No")) -> dict:
    return {"id": mid, "conditionId": "c" + mid, "question": question,
            "outcomes": list(outcomes), "outcomePrices": [yes, no],
            "bestBid": bid, "bestAsk": ask, "liquidity": 1000.0,
            "era": "numeric"}


def pi_row(cid: int, name: str, yes: float, no: float,
           market: str = "a market") -> dict:
    return {"market_id": 1, "market_name": market, "contract_id": cid,
            "name": name, "bestBuyYesCost": yes, "bestBuyNoCost": no,
            "bestSellYesCost": yes - 0.01, "bestSellNoCost": no - 0.01,
            "lastTradePrice": yes}


# --------------------------------------------------------------------------
# fees
# --------------------------------------------------------------------------

@pytest.mark.parametrize("price,contracts,expected", [
    # 0.07 * C * P * (1-P), rounded UP to the next whole cent, per order.
    (0.50, 1, 0.02),      # 0.0175  -> 2c
    (0.50, 100, 1.75),    # 1.75 exactly -> no rounding up
    (0.50, 10, 0.18),     # 0.175   -> 18c
    (0.25, 1, 0.02),      # 0.013125 -> 2c
    (0.75, 1, 0.02),      # symmetric in P <-> 1-P
    (0.10, 1, 0.01),      # 0.0063  -> the one-cent floor
    (0.01, 1, 0.01),      # 0.000693 -> still a full cent
    (0.99, 1, 0.01),
    (0.20, 10, 0.12),     # 0.112   -> 12c
    (0.87, 1, 0.01),      # 0.0079  -> 1c  (the real inversion below)
    (0.88, 1, 0.01),      # 0.0074  -> 1c
])
def test_kalshi_taker_fee_matches_hand_computation(price, contracts, expected):
    assert fees.kalshi_taker_fee(price, contracts) == pytest.approx(expected)


def test_kalshi_fee_is_zero_at_the_boundaries():
    """A contract at 0 or 1 carries no risk, so there is nothing to charge."""
    assert fees.kalshi_taker_fee(0.0) == 0.0
    assert fees.kalshi_taker_fee(1.0) == 0.0
    assert fees.kalshi_taker_fee(0.5, 0) == 0.0


def test_kalshi_fee_is_symmetric_in_price():
    for p in (0.03, 0.17, 0.44, 0.61, 0.92):
        assert fees.kalshi_taker_fee(p) == fees.kalshi_taker_fee(round(1 - p, 10))


def test_unrounded_model_undercharges_at_the_tails():
    """Why the rounding is the whole point: at 1c the old model charged 1/14th."""
    unrounded = 0.07 * 0.01 * 0.99
    assert unrounded == pytest.approx(0.000693)
    assert fees.kalshi_taker_fee(0.01) == 0.01
    assert fees.kalshi_taker_fee(0.01) > 14 * unrounded


def test_reduced_multiplier_table_is_empty_and_documented():
    """The owner fills this from the fee-schedule PDF; nothing here guesses it."""
    assert fees.KALSHI_REDUCED_TAKER_MULTIPLIER == {}
    assert fees.kalshi_taker_multiplier("KXINXY") == fees.KALSHI_TAKER_MULTIPLIER
    caveats = " ".join(fees.FEE_MODELS["kalshi"].caveats)
    assert "EMPTY" in caveats


def test_reduced_multiplier_is_honoured_when_filled(monkeypatch):
    monkeypatch.setitem(fees.KALSHI_REDUCED_TAKER_MULTIPLIER, "KXTEST",
                        fees.Decimal("0.035"))
    # 0.035 * 0.25 = 0.00875 -> 1c, against 0.0175 -> 2c on the general rate.
    assert fees.kalshi_taker_fee(0.50, 1, "KXTEST") == pytest.approx(0.01)
    assert fees.kalshi_taker_fee(0.50, 1, "KXOTHER") == pytest.approx(0.02)


def test_polymarket_fee_defaults_to_zero_with_a_working_override():
    assert fees.polymarket_taker_fee(0.5) == 0.0
    fees.POLYMARKET_TAKER_OVERRIDES["m1"] = 0.02
    try:
        assert fees.polymarket_taker_fee(0.50, 1.0, "m1") == pytest.approx(0.01)
    finally:
        fees.POLYMARKET_TAKER_OVERRIDES.pop("m1")


def test_predictit_fees_hand_computed():
    # 10% of profit on a winner, nothing on a loser.
    assert fees.predictit_profit_fee(0.40) == pytest.approx(0.06)
    assert fees.predictit_profit_fee(1.00) == 0.0
    assert fees.predictit_withdrawal_fee(0.94) == pytest.approx(0.047)
    # A pair at 45/45: gross 10c. Worst case is the 45c leg winning, profit
    # 55c, fee 5.5c, proceeds 94.5c, minus the 90c of cost = 4.5c.
    assert fees.predictit_pair_net_edge(0.45, 0.45, withdraw=False) == \
        pytest.approx(0.045)
    # With the 5% withdrawal: 0.945 * 0.95 = 0.89775, i.e. a 0.225c LOSS.
    assert fees.predictit_pair_net_edge(0.45, 0.45, withdraw=True) == \
        pytest.approx(-0.00225)


def test_predictit_needs_far_more_slack_than_kalshi():
    """The headline reason the two venues' net columns look nothing alike."""
    need = complement.predictit_breakeven_gross_edge(0.45, 0.45)
    assert need > 0.10                       # over ten cents before it exists
    assert fees.kalshi_pair_fee(0.45, 0.45) == pytest.approx(0.04)


# --------------------------------------------------------------------------
# ladders: the planted inversion
# --------------------------------------------------------------------------

def planted_ladder_rows() -> list[dict]:
    """Five rungs of one event with exactly one 1.0c gross inversion.

    P(>= s) must fall with s. Strikes 4.00/4.25/4.50/4.75/5.00 are quoted
    88/86, 87/87... deliberately: the 4.50 rung BIDS 0.88 while the 4.25
    rung ASKS 0.87, so a higher strike is bid over a lower strike's ask by
    one cent. Every other adjacent pair is clean.

    Net: both legs are taker orders. 0.07*0.87*0.13 = 0.0079 -> 1c and
    0.07*0.88*0.12 = 0.0074 -> 1c, so the two-cent fee turns a one-cent
    gross edge into a one-cent loss. Gross 1, net 0.
    """
    ev = "KXTESTLADDER-26"
    return [
        kmarket(f"{ev}-T4.00", ev, 0.90, 0.92, sub_title="Above 4.00%"),
        kmarket(f"{ev}-T4.25", ev, 0.85, 0.87, sub_title="Above 4.25%"),
        kmarket(f"{ev}-T4.50", ev, 0.88, 0.90, sub_title="Above 4.50%"),  # <-- planted
        kmarket(f"{ev}-T4.75", ev, 0.60, 0.62, sub_title="Above 4.75%"),
        kmarket(f"{ev}-T5.00", ev, 0.30, 0.32, sub_title="Above 5.00%"),
    ]


def test_planted_inversion_is_erased_by_fees():
    rep = ladders.screen_ladders(planted_ladder_rows())
    assert rep.ladders == 1
    assert rep.rungs == 5
    assert rep.adjacent_pairs == 4
    assert rep.inversions_gross == 1
    assert rep.inversions_net == 0
    i = rep.worst_inversion
    assert i is not None
    assert (i.lower_threshold, i.upper_threshold) == (4.25, 4.50)
    assert i.gross_edge == pytest.approx(0.01)
    assert i.fee == pytest.approx(0.02)
    assert i.net_edge == pytest.approx(-0.01)


def test_a_wide_inversion_does_survive_the_fee():
    """The screen is not rigged to always answer zero: widen the gap and the
    net count goes to one."""
    rows = planted_ladder_rows()
    rows[2]["yes_bid"], rows[2]["yes_ask"] = 0.95, 0.97
    rows[2]["no_bid"], rows[2]["no_ask"] = 0.03, 0.05
    rep = ladders.screen_ladders(rows)
    assert rep.inversions_gross == 1
    assert rep.inversions_net == 1
    assert rep.worst_net_inversion.net_edge == pytest.approx(0.08 - 0.02)


def test_structured_strike_fields_are_preferred_over_titles():
    """The strike comes from the venue even when no title regex matches."""
    ev = "KXSTRUCT-26"
    rows = [
        kmarket(f"{ev}-A", ev, 0.70, 0.72, sub_title="stays under 100 all year",
                strike_type="greater", floor_strike=100.0),
        kmarket(f"{ev}-B", ev, 0.50, 0.52, sub_title="stays under 110 all year",
                strike_type="greater", floor_strike=110.0),
        kmarket(f"{ev}-C", ev, 0.30, 0.32, sub_title="stays under 120 all year",
                strike_type="greater", floor_strike=120.0),
    ]
    lads = ladders.build_ladders(rows)
    assert len(lads) == 1
    assert lads[0].source == "strike"
    assert [r.threshold for r in lads[0].rungs] == [100.0, 110.0, 120.0]


def test_two_opposite_ladders_in_one_event_do_not_merge():
    """KXNFLSPREAD lists both teams' spreads as strike_type="greater" in one
    event. Merging them invented a 35c "arbitrage" out of two markets that
    can both settle YES."""
    ev = "KXNFLSPREAD-26SEP13ATLPIT"
    rows = [kmarket(f"{ev}-PIT{i}", ev, b, b + 0.01, strike_type="greater",
                    floor_strike=s,
                    sub_title=f"Pittsburgh wins by over {s} points")
            for i, (s, b) in enumerate(((2.5, 0.65), (4.5, 0.53), (6.5, 0.47)))]
    rows += [kmarket(f"{ev}-ATL{i}", ev, b, b + 0.01, strike_type="greater",
                     floor_strike=s,
                     sub_title=f"Atlanta wins by over {s} points")
             for i, (s, b) in enumerate(((1.5, 0.28), (5.5, 0.18), (9.5, 0.10)))]
    lads = ladders.build_ladders(rows)
    assert len(lads) == 2
    assert {lad.shape for lad in lads} == {
        "pittsburgh wins by over # points", "atlanta wins by over # points"}
    assert ladders.screen_ladders(rows).inversions_gross == 0


def test_equality_buckets_wearing_a_less_strike_are_refused():
    """KXSTARSHIPSPACE-26 lists "exactly 5", "exactly 6" ... as
    strike_type="less" with floor_strike == cap_strike -- structurally
    identical to a real "6,300 or below" CDF rung. Only the sub-title can
    tell them apart, so a bare-number sub-title is not a rung."""
    ev = "KXSTARSHIPSPACE-26"
    rows = [kmarket(f"{ev}-{n}.0", ev, b, a, strike_type="less",
                    floor_strike=float(n), cap_strike=float(n),
                    sub_title=str(n))
            for n, b, a in ((3, 0.08, 0.11), (4, 0.36, 0.40),
                            (5, 0.51, 0.55), (6, 0.01, 0.04))]
    assert ladders.build_ladders(rows) == []
    assert ladders.screen_ladders(rows).inversions_gross == 0

    # The same structural shape WITH a directional sub-title is a real rung.
    cdf = [kmarket(f"KXINXMINY-{n}", "KXINXMINY-01JAN2027", b, a,
                   strike_type="less", floor_strike=float(n),
                   cap_strike=float(n), sub_title=f"{n:,} or below")
           for n, b, a in ((5900, 0.088, 0.089), (6000, 0.128, 0.129),
                           (6100, 0.086, 0.098), (6200, 0.096, 0.105))]
    lads = ladders.build_ladders(cdf)
    assert len(lads) == 1 and len(lads[0].rungs) == 4


def test_less_strikes_are_flipped_into_p_ge():
    """A "less" rung quotes P(<= cap); the complement interval flips sides."""
    ev = "KXLESS-26"
    rows = [kmarket(f"{ev}-{i}", ev, 0.20, 0.24, strike_type="less",
                    cap_strike=float(s), sub_title=f"{s} or below")
            for i, s in enumerate((10, 20, 30))]
    lads = ladders.build_ladders(rows)
    assert len(lads) == 1
    r = lads[0].rungs[0]
    assert r.flipped is True
    assert (r.bid, r.ask) == pytest.approx((0.76, 0.80))
    # and a "less" ladder never merges with a "greater" one on the same event
    rows += [kmarket(f"{ev}-G{i}", ev, 0.5, 0.52, strike_type="greater",
                     floor_strike=float(s), sub_title=f"Above {s}")
             for i, s in enumerate((10, 20, 30))]
    assert {lad.unit for lad in ladders.build_ladders(rows)} == \
        {"strike:less", "strike:greater"}


def test_duplicate_strike_does_not_create_a_rung():
    ev = "KXDUP-26"
    rows = [kmarket(f"{ev}-{i}", ev, 0.5, 0.52, sub_title=t) for i, t in
            enumerate(("Above 10", "Above 10", "Above 20", "Above 30"))]
    lads = ladders.build_ladders(rows)
    assert [r.threshold for r in lads[0].rungs] == [10.0, 20.0, 30.0]


def test_implied_pmf_sums_to_one_and_finds_negative_mass():
    rows = planted_ladder_rows()
    lad = ladders.build_ladders(rows)[0]
    pmf = ladders.implied_pmf(lad)
    assert sum(m for _lo, _hi, m in pmf) == pytest.approx(1.0)
    assert any(m < 0 for _lo, _hi, m in pmf)
    neg = ladders.ladder_negative_mass(lad)
    assert len(neg) == 1
    assert neg[0].mass == pytest.approx(0.86 - 0.89)


def test_ladder_needs_three_rungs():
    ev = "KXSHORT-26"
    rows = [kmarket(f"{ev}-{i}", ev, 0.5, 0.52, sub_title=f"Above {s}")
            for i, s in enumerate((10, 20))]
    assert ladders.build_ladders(rows) == []


def test_unquoted_and_one_sided_rungs_are_ignored():
    ev = "KXQ-26"
    rows = [kmarket(f"{ev}-{i}", ev, b, a, sub_title=f"Above {s}")
            for i, (s, b, a) in enumerate(
                ((10, 0.5, 0.52), (20, 0.0, 0.40), (30, 0.2, 0.22),
                 (40, 0.1, 0.12)))]
    lad = ladders.build_ladders(rows)[0]
    assert [r.threshold for r in lad.rungs] == [10.0, 30.0, 40.0]


# --------------------------------------------------------------------------
# ladders: one fixture per legacy title family
# --------------------------------------------------------------------------

LEGACY_TITLE_CASES = [
    # (family, three sub-titles from the real archive, expected thresholds)
    ("above_k", ("Above 220K", "Above 230K", "Above 240K"),
     [220_000.0, 230_000.0, 240_000.0]),
    ("above_pct", ("Above 0.0%", "Above 0.5%", "Above 1.5%"),
     [0.0, 0.5, 1.5]),
    ("at_least_pct", ("At least 60%", "At least 65%", "At least 70%"),
     [60.0, 65.0, 70.0]),
    ("above_m", ("Above 2.6M", "Above 2.8M", "Above 3M"),
     [2_600_000.0, 2_800_000.0, 3_000_000.0]),
    ("above_million", ("Above 405 million", "Above 410 million",
                       "Above 415 million"),
     [405e6, 410e6, 415e6]),
    ("above_billion", ("Above 54.5 billion", "Above 55 billion",
                       "Above 55.5 billion"),
     [54.5e9, 55e9, 55.5e9]),
    ("above_thousand", ("Above 189 thousand", "Above 192 thousand",
                        "Above 195 thousand"),
     [189e3, 192e3, 195e3]),
    ("party_margin", ("Republicans, 26+ pts", "Republicans, 28+ pts",
                      "Republicans, 30+ pts"),
     [26.0, 28.0, 30.0]),
    ("or_above", ("36 or more", "38 or more", "40 or more"),
     [36.0, 38.0, 40.0]),
    ("or_above", ("10,600.0001 or above", "10,700 or above",
                  "10,800 or above"),
     [10_600.0001, 10_700.0, 10_800.0]),
    ("pct_or_above", ("6.1% or Above", "6.5% or Above", "7.0% or Above"),
     [6.1, 6.5, 7.0]),
    ("at_or_above", ("At or above 55", "At or above 60", "At or above 65"),
     [55.0, 60.0, 65.0]),
    ("above_plain", ("Above 800", "Above 900", "Above 1,000"),
     [800.0, 900.0, 1000.0]),
    ("at_least", ("At least 440", "At least 445", "At least 450"),
     [440.0, 445.0, 450.0]),
    ("above_plain", ("Above $25.00", "Above $35.00", "Above $45.00"),
     [25.0, 35.0, 45.0]),
]


@pytest.mark.parametrize("family,titles,expected", LEGACY_TITLE_CASES)
def test_legacy_title_family_parses_into_one_ladder(family, titles, expected):
    ev = f"KX{family.upper()}-26"
    rows = [kmarket(f"{ev}-{i}", ev, 0.50 - 0.1 * i, 0.52 - 0.1 * i,
                    sub_title=t) for i, t in enumerate(titles)]
    lads = ladders.build_ladders(rows)
    assert len(lads) == 1, f"{family}: {titles}"
    assert lads[0].source == "title"
    assert lads[0].family == family
    assert [r.threshold for r in lads[0].rungs] == pytest.approx(expected)


def test_mixed_units_in_one_event_still_make_one_ladder():
    """"Above 900K" and "Above 1M" are two rungs of the same curve."""
    ev = "KXMIX-26"
    rows = [kmarket(f"{ev}-{i}", ev, 0.5 - 0.1 * i, 0.52 - 0.1 * i, sub_title=t)
            for i, t in enumerate(("Above 900K", "Above 1M", "Above 1.1M"))]
    lads = ladders.build_ladders(rows)
    assert len(lads) == 1
    assert [r.threshold for r in lads[0].rungs] == [900_000.0, 1e6, 1.1e6]


def test_percent_and_scalar_strikes_never_share_a_ladder():
    ev = "KXUNIT-26"
    rows = [kmarket(f"{ev}-p{i}", ev, 0.5, 0.52, sub_title=f"Above {v}%")
            for i, v in enumerate((1, 2, 3))]
    rows += [kmarket(f"{ev}-s{i}", ev, 0.5, 0.52, sub_title=f"Above {v}")
             for i, v in enumerate((10, 20, 30))]
    assert {lad.unit for lad in ladders.build_ladders(rows)} == \
        {"percent", "scalar"}


def test_party_margins_of_different_parties_never_share_a_ladder():
    ev = "KXMOV-26"
    rows = [kmarket(f"{ev}-r{i}", ev, 0.5, 0.52,
                    sub_title=f"Republicans, {v}+ pts")
            for i, v in enumerate((2, 4, 6))]
    rows += [kmarket(f"{ev}-d{i}", ev, 0.5, 0.52,
                     sub_title=f"Democrats, {v}+ pts")
             for i, v in enumerate((2, 4, 6))]
    assert {lad.unit for lad in ladders.build_ladders(rows)} == \
        {"margin:republicans", "margin:democrats"}


@pytest.mark.parametrize("title", [
    "Before Jan 1, 2030", "Yes", "Tie", "Democratic party", "The Odyssey",
    "Proposition 12", "Question 4", "5% to 10%", "", "Dune: Part Three",
])
def test_non_threshold_titles_are_not_parsed_as_rungs(title):
    assert ladders.parse_title_threshold(title) is None


# --------------------------------------------------------------------------
# complement
# --------------------------------------------------------------------------

def test_kalshi_identity_holds_on_well_formed_rows_and_fails_when_broken():
    ev = "KXID-26"
    rows = [kmarket(f"{ev}-{i}", ev, 0.30, 0.34) for i in range(5)]
    ident = complement.kalshi_identity(rows)
    assert (ident.checked, ident.deviations) == (5, 0)
    assert complement.assert_kalshi_identity(rows).holds

    rows[2]["no_ask"] = 0.55                      # the venue's mirror breaks
    broken = complement.kalshi_identity(rows)
    assert broken.deviations == 1
    assert broken.examples[0]["ticker"] == f"{ev}-2"
    with pytest.raises(complement.BrokenInvariant) as exc:
        complement.assert_kalshi_identity(rows, where="unit test")
    assert "re-derive the screen" in str(exc.value)


def test_kalshi_identity_holds_on_every_archive_fixture():
    for fx in sorted((ROOT / "tests" / "fixtures").glob("*.json.gz")):
        snap = load_snapshot(fx)
        ident = complement.kalshi_identity(snap.kalshi)
        assert ident.deviations == 0, fx.name
        assert ident.checked > 0, fx.name


def test_polymarket_complement_finds_the_planted_violation():
    rows = [
        poly_row("1", "clean", 0.40, 0.60, bid=0.39, ask=0.41),
        poly_row("2", "also clean", 0.55, 0.45, bid=0.54, ask=0.56),
        poly_row("3", "planted underround", 0.30, 0.60, bid=0.29, ask=0.31),
        poly_row("4", "not complementary", 0.30, 0.30,
                 outcomes=("Lille OSC", "Angers SCO")),
    ]
    rep = complement.screen_polymarket(rows)
    assert rep.pairs == 3                     # the football row is excluded
    assert rep.gross == 1
    assert rep.worst.market_id == "3"
    assert rep.worst.gross_edge == pytest.approx(0.10)
    # Polymarket charges nothing today, so net equals gross and the table
    # says so rather than quietly printing one number twice.
    assert rep.net == 1
    assert rep.worst.fee == 0.0


def test_polymarket_fee_override_can_erase_a_violation():
    rows = [poly_row("9", "thin edge", 0.49, 0.50, bid=0.48, ask=0.50)]
    assert complement.screen_polymarket(rows).net == 1
    fees.POLYMARKET_TAKER_OVERRIDES["c9"] = 0.02      # keyed on conditionId
    try:
        rep = complement.screen_polymarket(rows)
        assert rep.gross == 1
        assert rep.net == 0
    finally:
        fees.POLYMARKET_TAKER_OVERRIDES.pop("c9")


def test_polymarket_crossed_book_is_counted_separately():
    rows = [poly_row("1", "crossed", 0.50, 0.50, bid=0.60, ask=0.40)]
    rep = complement.screen_polymarket(rows)
    assert rep.crossed_books == 1
    assert rep.gross == 0                      # prices still sum to 1


def test_predictit_complement_finds_the_planted_violation():
    rows = [
        pi_row(1, "clean", 0.52, 0.50),
        pi_row(2, "clean too", 0.23, 0.78),
        pi_row(3, "planted 8c underround", 0.45, 0.47),
    ]
    rep = complement.screen_predictit(rows)
    assert rep.pairs == 3
    assert rep.gross == 1
    assert rep.worst.contract_id == "3"
    assert rep.worst.gross_edge == pytest.approx(0.08)
    # 8c gross is not enough: the 45c leg winning pays 5.5c of profit fee and
    # 4.7c of withdrawal, so the pair loses money.
    assert rep.worst.net_edge < 0
    assert rep.net == 0


def test_predictit_violation_wide_enough_does_survive():
    rows = [pi_row(1, "wide", 0.40, 0.40)]
    rep = complement.screen_predictit(rows)
    assert rep.gross == 1
    assert rep.net == 1                        # 20c gross beats ~10.7c of fee


# --------------------------------------------------------------------------
# buckets
# --------------------------------------------------------------------------

def test_bucket_sum_candidate_gross_and_net():
    ev = "KXBUCKET-26"
    rows = [kmarket(f"{ev}-{i}", ev, a - 0.02, a, mutually_exclusive=True,
                    title="a mutually exclusive event")
            for i, a in enumerate((0.30, 0.30, 0.33))]
    rep = buckets.screen_buckets(rows)
    assert (rep.events, rep.screened) == (1, 1)
    assert rep.gross == 1
    # 0.93 of asks, three legs of fee at 2c each -> 0.99 < 1, still net.
    assert rep.worst.gross_edge == pytest.approx(0.07)
    assert rep.worst.fee == pytest.approx(0.06)
    assert rep.net == 1


def test_many_legs_of_fee_kill_a_thin_bucket_candidate():
    ev = "KXMANY-26"
    rows = [kmarket(f"{ev}-{i}", ev, 0.07, 0.09, mutually_exclusive=True)
            for i in range(11)]                      # 0.99 of asks, 11c of fee
    rep = buckets.screen_buckets(rows)
    assert rep.gross == 1
    assert rep.net == 0


def test_a_bucket_with_no_ask_disqualifies_the_event():
    """The missing bucket is usually the favourite; counting without it
    manufactures an underround."""
    ev = "KXGAP-26"
    rows = [kmarket(f"{ev}-{i}", ev, 0.10, 0.12, mutually_exclusive=True)
            for i in range(4)]
    rows[1]["yes_ask"] = None
    rep = buckets.screen_buckets(rows)
    assert rep.events == 1 and rep.screened == 0 and rep.gross == 0


def test_two_bucket_events_are_left_to_the_complement_screen():
    ev = "KXTWO-26"
    rows = [kmarket(f"{ev}-{i}", ev, 0.30, 0.32, mutually_exclusive=True)
            for i in range(2)]
    assert buckets.screen_buckets(rows).screened == 0


def test_ordinary_overround_is_not_a_candidate():
    ev = "KXOVER-26"
    rows = [kmarket(f"{ev}-{i}", ev, 0.38, 0.40, mutually_exclusive=True)
            for i in range(3)]
    rep = buckets.screen_buckets(rows)
    assert rep.screened == 1 and rep.gross == 0
    assert rep.median_ask_sum == pytest.approx(1.20)


# --------------------------------------------------------------------------
# replay end to end
# --------------------------------------------------------------------------

def write_synthetic_snapshot(path: Path, t: str, inverted: bool) -> None:
    """A whole v1-shaped snapshot with one ladder, one poly and one PI row."""
    ev = "KXTESTLADDER-26"
    subs = ("Above 4.00%", "Above 4.25%", "Above 4.50%", "Above 4.75%")
    quotes = [(0.90, 0.92), (0.85, 0.87),
              (0.88, 0.90) if inverted else (0.80, 0.82), (0.60, 0.62)]
    markets = [{"ticker": f"{ev}-{i}", "title": "test", "yes_sub_title": s,
                "yes_bid_dollars": f"{b:.4f}", "yes_ask_dollars": f"{a:.4f}",
                "no_bid_dollars": f"{1 - a:.4f}", "no_ask_dollars": f"{1 - b:.4f}",
                "last_price_dollars": f"{b:.4f}", "volume_fp": "1",
                "open_interest_fp": "1", "close_time": "2027-01-01T00:00:00Z",
                "status": "active"}
               for i, (s, (b, a)) in enumerate(zip(subs, quotes))]
    doc = {"t": t, "venues": {
        "kalshi": [{"event_ticker": ev, "series_ticker": "KXTESTLADDER",
                    "category": "Economics", "sub_title": "test",
                    "mutually_exclusive": False, "markets": markets}],
        "polymarket": [{"id": "1", "question": "q", "slug": "q",
                        "endDate": "2027-01-01T00:00:00Z", "liquidity": "1000",
                        "bestBid": 0.29, "bestAsk": 0.31,
                        "outcomes": '["Yes", "No"]',
                        "outcomePrices": '["0.30", "0.60"]',
                        "conditionId": "c1"}],
        "predictit": [{"id": 1, "name": "m", "contracts": [
            {"id": 1, "name": "c", "bestBuyYesCost": 0.45,
             "bestBuyNoCost": 0.47, "bestSellYesCost": 0.44,
             "bestSellNoCost": 0.46, "lastTradePrice": 0.45}]}],
        "manifold": []}, "errors": {}}
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(doc, fh)


def test_replay_over_a_synthetic_archive(tmp_path):
    root = tmp_path / "data"
    write_synthetic_snapshot(root / "20260901" / "0100Z.json.gz",
                             "2026-09-01T01:00:00Z", inverted=False)
    write_synthetic_snapshot(root / "20260901" / "0400Z.json.gz",
                             "2026-09-01T04:00:00Z", inverted=True)
    out = tmp_path / "results"
    rc = replay_mod.main(["--roots", str(root), "--out", str(out),
                          "--settlements", str(tmp_path / "no-settlements"),
                          "--events", str(tmp_path / "no-events.yaml"),
                          "--no-plots", "--quiet"])
    assert rc == 0
    with open(out / "summary.json", encoding="utf-8") as fh:
        s = json.load(fh)
    assert s["archive"]["snapshots"] == 2
    assert s["archive"]["first_snapshot"] == "2026-09-01T01:00:00Z"
    assert s["archive"]["median_gap_hours"] == pytest.approx(3.0)
    assert len(s["archive"]["identity_sha256"]) == 64
    assert s["ladders"]["inversions_gross_total"] == 1
    assert s["ladders"]["inversions_net_total"] == 0
    assert s["ladders"]["snapshots_with_gross_inversion"] == 1
    assert s["kalshi_identity"]["deviations_total"] == 0
    assert s["polymarket_complement"]["gross_total"] == 2
    assert s["predictit_complement"]["gross_total"] == 2
    assert s["predictit_complement"]["net_total"] == 0

    lines = (out / "timeseries.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0].split(",") == list(replay_mod.COLUMNS)
    assert len(lines) == 3
    body = (out / "README.md").read_text(encoding="utf-8")
    assert s["archive"]["identity_sha256"] in body
    assert "gross" in body and "net" in body


def test_replay_of_an_empty_archive_is_green_not_red(tmp_path, capsys):
    assert replay_mod.main(["--roots", str(tmp_path / "nothing"),
                            "--out", str(tmp_path / "out"), "--quiet"]) == 0
    assert "nothing to replay" in capsys.readouterr().out


def test_replay_fails_loudly_on_a_broken_kalshi_identity(tmp_path):
    """A venue data-model change must stop the build, not become a result."""
    p = tmp_path / "data" / "20260901" / "0100Z.json.gz"
    write_synthetic_snapshot(p, "2026-09-01T01:00:00Z", inverted=False)
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        doc = json.load(fh)
    doc["venues"]["kalshi"][0]["markets"][0]["no_ask_dollars"] = "0.5000"
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        json.dump(doc, fh)
    with pytest.raises(complement.BrokenInvariant):
        replay_mod.main(["--roots", str(tmp_path / "data"),
                         "--out", str(tmp_path / "out"),
                         "--settlements", str(tmp_path / "no-settlements"),
                         "--events", str(tmp_path / "no-events.yaml"),
                         "--no-plots", "--quiet"])


def test_replay_is_byte_stable_across_runs(tmp_path):
    """CI commits results/ daily; a re-run that changes nothing must produce
    the same bytes, or the archive fills with commits that say nothing."""
    root = tmp_path / "data"
    write_synthetic_snapshot(root / "20260901" / "0100Z.json.gz",
                             "2026-09-01T01:00:00Z", inverted=True)
    out = tmp_path / "results"
    args = ["--roots", str(root), "--out", str(out), "--no-plots", "--quiet"]
    assert replay_mod.main(args) == 0
    first = {p.name: p.read_bytes() for p in sorted(out.iterdir())}
    assert replay_mod.main(args) == 0
    second = {p.name: p.read_bytes() for p in sorted(out.iterdir())}
    assert first == second


def test_a_changed_snapshot_changes_the_result(tmp_path):
    root = tmp_path / "data"
    snap = root / "20260901" / "0100Z.json.gz"
    out = tmp_path / "results"
    args = ["--roots", str(root), "--out", str(out), "--no-plots", "--quiet"]
    write_synthetic_snapshot(snap, "2026-09-01T01:00:00Z", inverted=False)
    replay_mod.main(args)
    before = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    write_synthetic_snapshot(snap, "2026-09-01T01:00:00Z", inverted=True)
    replay_mod.main(args)
    after = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert before["ladders"]["inversions_gross_total"] == 0
    assert after["ladders"]["inversions_gross_total"] == 1
    assert after["archive"]["identity_sha256"] != before["archive"]["identity_sha256"]


def test_archive_identity_changes_with_the_bytes(tmp_path):
    a = tmp_path / "data" / "20260901" / "0100Z.json.gz"
    write_synthetic_snapshot(a, "2026-09-01T01:00:00Z", inverted=False)
    first = replay_mod.archive_identity([a])
    write_synthetic_snapshot(a, "2026-09-01T01:00:00Z", inverted=True)
    assert replay_mod.archive_identity([a]) != first


# --------------------------------------------------------------------------
# the README drift check
# --------------------------------------------------------------------------

CHECK = ROOT / "scripts" / "check_readme.py"


def run_check(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CHECK), *args],
                          capture_output=True, text=True, cwd=ROOT)


def test_check_readme_passes_on_matching_numbers(tmp_path):
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"ladders": {"median_per_snapshot": 1114},
                                   "archive": {"days_spanned": 19.15}}),
                       encoding="utf-8")
    readme = tmp_path / "README.md"
    readme.write_text(
        "about 1,114 <!-- results:ladders.median_per_snapshot --> ladders "
        "over 19.2 <!-- results:archive.days_spanned --> days\n",
        encoding="utf-8")
    r = run_check(["--readme", str(readme), "--summary", str(summary)])
    assert r.returncode == 0, r.stderr
    assert "2 number(s) match" in r.stdout


def test_check_readme_fails_on_drift_and_repairs_with_write(tmp_path):
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"ladders": {"median_per_snapshot": 1114}}),
                       encoding="utf-8")
    readme = tmp_path / "README.md"
    readme.write_text("44 <!-- results:ladders.median_per_snapshot --> ladders\n",
                      encoding="utf-8")
    r = run_check(["--readme", str(readme), "--summary", str(summary)])
    assert r.returncode == 1
    assert "says 1114 but the README says 44" in r.stderr

    r = run_check(["--readme", str(readme), "--summary", str(summary), "--write"])
    assert r.returncode == 0, r.stderr
    assert readme.read_text(encoding="utf-8").startswith("1114 <!--")
    assert run_check(["--readme", str(readme),
                      "--summary", str(summary)]).returncode == 0


def test_check_readme_fails_on_an_unknown_key(tmp_path):
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"ladders": {}}), encoding="utf-8")
    readme = tmp_path / "README.md"
    readme.write_text("1 <!-- results:ladders.nope -->\n", encoding="utf-8")
    for extra in ([], ["--write"]):
        r = run_check(["--readme", str(readme), "--summary", str(summary),
                       *extra])
        assert r.returncode == 1
        assert "unknown results key" in r.stderr


def test_check_readme_fails_when_the_markers_are_deleted(tmp_path):
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"a": 1}), encoding="utf-8")
    readme = tmp_path / "README.md"
    readme.write_text("no markers here\n", encoding="utf-8")
    r = run_check(["--readme", str(readme), "--summary", str(summary)])
    assert r.returncode == 1
    assert "expected at least" in r.stderr


def test_check_readme_is_green_before_the_first_replay(tmp_path):
    r = run_check(["--readme", str(ROOT / "README.md"),
                   "--summary", str(tmp_path / "absent.json")])
    assert r.returncode == 0


def test_repo_readme_matches_the_committed_results():
    """The real check, on the real files, exactly as CI runs it."""
    if not (ROOT / "results" / "summary.json").exists():
        pytest.skip("no results committed yet")
    r = run_check([])
    assert r.returncode == 0, r.stdout + r.stderr
