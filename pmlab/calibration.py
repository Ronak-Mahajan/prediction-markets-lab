"""Resolution scoring: were the quotes right, and by how much?

Every other screen in this package asks whether a set of prices is
*coherent*. This one asks whether it was *correct*, which needs outcomes,
which is why it could not exist until ``settle.py`` started following
recorded markets to their settlement.

The join
--------

For each settled market and each horizon H in (1 d, 1 wk, 1 mo, 2 mo) the
quote scored is **the last quote recorded at or before ``settled_at - H``**,
and it is used only if it is no older than :data:`MAX_QUOTE_AGE_HOURS`
before that cut-off. The age cap is the whole reason this module can be
trusted: without it, a market that settled on 2026-09-10 and was last
quoted on 2026-08-23 would be scored as a "one day ahead" forecast when it
is really an eighteen-day-ahead one, and the 1 d column would silently fill
up with stale prices. 24 h is just under twice the worst gap the recorder
has actually produced (12.6 h against a 3.3 h median), so a market quoted
on the normal cadence always has a usable quote and a market the recorder
missed is reported missing rather than faked.

A horizon longer than the archive is therefore empty by construction, not
by accident: the archive opens on 2026-08-23, so nothing that settled
before 2026-09-23 can have a 1-month-ahead quote. Those cells report
``n = 0`` and say why.

What is scored
--------------

* **Brier score** ``mean((p - y)^2)`` and **log score**
  ``mean(y ln p + (1-y) ln(1-p))`` on the **mid**, against the 50/50
  baseline (Brier 0.25, log -0.6931). Skill is ``1 - brier / 0.25``.
* **Reliability curves** in 10 equal-width bins, each with a Wilson 95%
  interval *and* a block-bootstrap 95% interval. The two disagree on
  purpose: Wilson assumes the observations in a bin are independent
  Bernoulli draws, which markets settling on the same day are not. The
  blocks are ``(venue, settlement date)``, which is the coarsest honest
  unit of common shock in this data -- every NFL market on one Sunday
  resolves off the same afternoon. Where the bootstrap interval is much
  wider than the Wilson one, the Wilson one is the wrong one.
* **Favourite-longshot bias** measured separately **on the bid and on the
  ask**, never on the mid. A longshot buyer pays the ask and a favourite
  seller receives the bid; the mid is a price at which nobody traded. The
  reported bias is ``realised frequency - mean price`` in cents, so a
  negative number at the low end of the ask table means longshots were
  sold for more than they were worth.

Slices: venue, category, horizon and liquidity bucket. The liquidity
measure is each venue's own (Kalshi open interest in contracts, Polymarket
``liquidityNum`` in dollars, Manifold ``totalLiquidity``), so the buckets
are comparable *within* a venue and not across venues; the output names
the field it used. Category exists only on Kalshi -- the recorder captures
no category for Polymarket or Manifold -- so that slice is a Kalshi slice
and the table says so.

PredictIt is joined and reported but never enters a headline number: the
public feed carries open markets only, so ``settle.py`` infers an outcome
from the last trade of a contract that disappeared. An inferred outcome is
a guess about the answer, and scoring a forecast against a guess is not a
measurement.

Zero settlements is a supported state, not an error: the module returns an
empty report carrying the reason, the replay writes an empty table with a
note, and the exit code is zero. That is the state the repository is in
until enough recorded markets resolve.
"""
from __future__ import annotations

import json
import math
import random
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Sequence

from .archive import Snapshot, parse_json_list, parse_time, to_float

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

#: (label, days before settlement). Order is the reporting order.
HORIZONS: tuple[tuple[str, float], ...] = (
    ("1d", 1.0), ("1wk", 7.0), ("1mo", 30.0), ("2mo", 60.0),
)

#: A quote may be at most this old at the horizon cut-off. See the module
#: docstring: this is what stops a stale price being scored as a fresh one.
MAX_QUOTE_AGE_HOURS = 24.0

#: The forecast a coin flip would have made.
BASELINE_P = 0.5
BASELINE_BRIER = 0.25
BASELINE_LOG = math.log(0.5)

#: Probabilities are clipped before the log score, and the number of
#: clipped observations is reported next to it. A venue quoting 0.00/0.00
#: on a market that settled YES has made an infinitely bad forecast; the
#: clip bounds how much one such quote can dominate the mean, and the
#: count says how often the bound was needed.
LOG_CLIP = 1e-4

RELIABILITY_BINS = 10

#: Block bootstrap. Fixed seed: this output is committed by CI and must be
#: byte-identical on a re-run of the same archive.
BOOTSTRAP_DRAWS = 1000
BOOTSTRAP_SEED = 20260911
BOOTSTRAP_ALPHA = 0.05

#: Resampling two blocks with replacement draws the same two blocks a
#: quarter of the time, and the "interval" that comes out is an artefact of
#: the block count rather than a statement about the data -- a Kalshi slice
#: whose settlements all landed on one day produced [1.000, 1.000]. Below
#: this many blocks no bootstrap interval is reported and the block count
#: is reported instead.
MIN_BOOTSTRAP_BLOCKS = 3

#: Venue-native liquidity bands. Units differ by venue (contracts of open
#: interest on Kalshi, dollars on Polymarket, Manifold liquidity units), so
#: these compare markets inside a venue and never across venues.
LIQUIDITY_BANDS: tuple[tuple[str, float, float], ...] = (
    ("<100", 0.0, 100.0),
    ("100-1k", 100.0, 1_000.0),
    ("1k-10k", 1_000.0, 10_000.0),
    ("10k-100k", 10_000.0, 100_000.0),
    (">=100k", 100_000.0, float("inf")),
)

LIQUIDITY_FIELD = {
    "kalshi": "open_interest (contracts)",
    "polymarket": "liquidityNum (USD)",
    "manifold": "totalLiquidity",
    "predictit": "none recorded",
}

#: Venues whose outcomes are observed rather than inferred. Only these
#: enter a headline number.
HEADLINE_VENUES = ("kalshi", "polymarket", "manifold")

EMPTY_NOTE = ("No settled market in this archive has a recorded quote at "
              "any scored horizon, so every calibration table below is "
              "empty. This is the expected state until recorded markets "
              "resolve; it is not a failure.")


# --------------------------------------------------------------------------
# Settlements
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Settlement:
    """One market that resolved, reduced to what scoring needs."""

    venue: str
    key: str                    # the id the snapshots quote this market under
    outcome: float              # 1.0 or 0.0, for the side the quote prices
    settled_at: datetime
    question: str = ""
    inferred: bool = False      # PredictIt: outcome guessed, never headline
    block: str = ""             # bootstrap block key


@dataclass
class SettlementSet:
    by_venue: dict[str, dict[str, Settlement]] = field(default_factory=dict)
    #: {venue: {reason: count}} for every settlement row that was not usable.
    excluded: dict[str, dict[str, int]] = field(default_factory=dict)
    files_read: int = 0
    roots: list[str] = field(default_factory=list)

    def total(self) -> int:
        return sum(len(v) for v in self.by_venue.values())

    def drop(self, venue: str, reason: str) -> None:
        self.excluded.setdefault(venue, {})
        self.excluded[venue][reason] = self.excluded[venue].get(reason, 0) + 1


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def _block_key(venue: str, when: datetime) -> str:
    """Bootstrap block: one venue, one settlement day."""
    return f"{venue}:{when.strftime('%Y-%m-%d')}"


def _kalshi_settlement(r: dict, s: SettlementSet) -> Settlement | None:
    ticker = r.get("ticker")
    result = str(r.get("result") or "").strip().lower()
    when = parse_time(r.get("settlement_ts") or r.get("settled_time"))
    if not ticker:
        s.drop("kalshi", "no ticker")
        return None
    if result not in ("yes", "no"):
        s.drop("kalshi", f"result={result or 'empty'!s}")
        return None
    if when is None:
        s.drop("kalshi", "no settlement time")
        return None
    return Settlement("kalshi", str(ticker), 1.0 if result == "yes" else 0.0,
                      when, str(r.get("event_ticker") or ""),
                      block=_block_key("kalshi", when))


def _polymarket_settlement(r: dict, s: SettlementSet) -> Settlement | None:
    mid = r.get("id")
    if mid is None:
        s.drop("polymarket", "no id")
        return None
    if r.get("umaResolutionStatus") != "resolved":
        s.drop("polymarket", "not resolved")
        return None
    outcomes = parse_json_list(r.get("outcomes")) or []
    prices = parse_json_list(r.get("outcomePrices")) or []
    if len(outcomes) != 2 or len(prices) != 2:
        s.drop("polymarket", "not a two-outcome market")
        return None
    # bestBid/bestAsk quote the FIRST token, so the first outcome price is
    # the outcome those quotes were forecasting.
    y = to_float(prices[0])
    if y not in (0.0, 1.0):
        s.drop("polymarket", "outcome price not 0 or 1")
        return None
    when = parse_time(r.get("closedTime"))
    if when is None:
        s.drop("polymarket", "no closedTime")
        return None
    return Settlement("polymarket", str(mid), y, when,
                      str(r.get("question") or "")[:200],
                      block=_block_key("polymarket", when))


def _manifold_settlement(r: dict, s: SettlementSet) -> Settlement | None:
    mid = r.get("id")
    if mid is None:
        s.drop("manifold", "no id")
        return None
    if r.get("missing"):
        s.drop("manifold", "market gone from the API")
        return None
    if not r.get("isResolved"):
        s.drop("manifold", "not resolved")
        return None
    res = str(r.get("resolution") or "").strip().upper()
    if res not in ("YES", "NO"):
        # MKT resolves to a probability and CANCEL pays everyone back.
        # Neither is a binary outcome, so neither is scoreable here.
        s.drop("manifold", f"resolution={res or 'empty'}")
        return None
    when = parse_time(r.get("resolutionTime"))
    if when is None:
        s.drop("manifold", "no resolutionTime")
        return None
    return Settlement("manifold", str(mid), 1.0 if res == "YES" else 0.0, when,
                      str(r.get("question") or "")[:200],
                      block=_block_key("manifold", when))


def _predictit_settlement(r: dict, s: SettlementSet) -> Settlement | None:
    cid = r.get("contract_id")
    if cid is None:
        s.drop("predictit", "no contract_id")
        return None
    out = r.get("inferred_outcome")
    if out not in ("yes", "no"):
        s.drop("predictit", "no inferrable outcome")
        return None
    when = parse_time(r.get("disappeared_by"))
    if when is None:
        s.drop("predictit", "no disappearance time")
        return None
    return Settlement("predictit", str(cid), 1.0 if out == "yes" else 0.0,
                      when, str(r.get("name") or "")[:200], inferred=True,
                      block=_block_key("predictit", when))


_READERS = {
    "kalshi": _kalshi_settlement,
    "polymarket": _polymarket_settlement,
    "manifold": _manifold_settlement,
    "predictit": _predictit_settlement,
}


def load_settlements(*roots: str | Path) -> SettlementSet:
    """Read ``<root>/<venue>/*.jsonl`` into one settlement per market.

    A market may be recorded several times as its status firms up (a
    Polymarket id is re-polled until ``umaResolutionStatus == "resolved"``,
    a Kalshi ticker can appear in both the head sweep and the backfill).
    The last usable record for a key wins, in file then line order.
    """
    out = SettlementSet(roots=[str(r) for r in roots])
    for root in roots:
        r = Path(root)
        if not r.is_dir():
            continue
        for venue, reader in _READERS.items():
            d = r / venue
            if not d.is_dir():
                continue
            for p in sorted(d.glob("*.jsonl")):
                out.files_read += 1
                for row in read_jsonl(p):
                    st = reader(row, out)
                    if st is not None:
                        out.by_venue.setdefault(venue, {})[st.key] = st
    return out


# --------------------------------------------------------------------------
# Scoring primitives (pure; the tests hand-compute every one of these)
# --------------------------------------------------------------------------

def brier_score(ps: Sequence[float], ys: Sequence[float]) -> float | None:
    """Mean squared error of a probabilistic forecast. Lower is better."""
    if not ps:
        return None
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ps)


def log_score(ps: Sequence[float], ys: Sequence[float],
              clip: float = LOG_CLIP) -> tuple[float | None, int]:
    """Mean log likelihood (natural log, higher is better) and the number
    of observations whose probability had to be clipped to compute it."""
    if not ps:
        return None, 0
    total, clipped = 0.0, 0
    for p, y in zip(ps, ys):
        q = p
        if q < clip:
            q, clipped = clip, clipped + 1
        elif q > 1.0 - clip:
            q, clipped = 1.0 - clip, clipped + 1
        total += math.log(q) if y >= 0.5 else math.log(1.0 - q)
    return total / len(ps), clipped


def skill(brier: float | None, baseline: float = BASELINE_BRIER) -> float | None:
    """Brier skill score against the 50/50 baseline: 1 is perfect, 0 is
    the coin flip, negative is worse than the coin flip."""
    if brier is None:
        return None
    return 1.0 - brier / baseline


def wilson_interval(k: int, n: int, z: float = 1.959963985) -> tuple[float, float]:
    """Wilson score interval for k successes in n trials (95% by default).

    >>> [round(v, 4) for v in wilson_interval(5, 10)]
    [0.2366, 0.7634]
    """
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    z2 = z * z
    denom = n + z2
    centre = (k + z2 / 2.0) / denom
    half = (z / denom) * math.sqrt(n * p * (1.0 - p) + z2 / 4.0)
    return (max(0.0, centre - half), min(1.0, centre + half))


def bin_index(p: float, nbins: int = RELIABILITY_BINS) -> int:
    """Which equal-width bin a probability falls in; 1.0 joins the top bin."""
    return min(nbins - 1, max(0, int(p * nbins)))


@dataclass(frozen=True)
class Observation:
    """One scored forecast."""

    venue: str
    key: str
    horizon: str
    outcome: float
    mid: float
    bid: float
    ask: float
    quote_t: datetime
    quote_age_hours: float
    settled_at: datetime
    liquidity: float | None
    liquidity_band: str
    category: str
    era: str
    block: str
    inferred: bool
    question: str = ""


def liquidity_band(x: float | None) -> str:
    if x is None:
        return "unknown"
    for label, lo, hi in LIQUIDITY_BANDS:
        if lo <= x < hi:
            return label
    return "unknown"


def _percentile(xs: list[float], q: float) -> float:
    """Nearest-rank percentile on a sorted copy; deterministic, no numpy.

    Used for the bootstrap's interval ends, where nearest-rank is the
    conventional choice and picking an existing draw is the point. Anything
    this module *calls* a median goes through :func:`_median` instead,
    because the nearest-rank "median" of two values is the lower one, and a
    column headed "median spread" that reports 10 for a 10 and a 20 is
    wrong in the way nobody checks.
    """
    if not xs:
        return float("nan")
    s = sorted(xs)
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[i]


def _median(xs: list[float]) -> float | None:
    return statistics.median(xs) if xs else None


def reliability(obs: Sequence[Observation], price: str = "mid",
                nbins: int = RELIABILITY_BINS,
                draws: int = BOOTSTRAP_DRAWS,
                seed: int = BOOTSTRAP_SEED) -> list[dict]:
    """Reliability table: one row per bin, with a Wilson and a block
    bootstrap interval on the realised frequency.

    The bootstrap resamples whole blocks (venue x settlement day) with
    replacement, because markets that settle together do not fail
    independently; the Wilson interval assumes they do. Both are reported
    so the reader can see how much of the apparent precision is the
    independence assumption.
    """
    rows = []
    for b in range(nbins):
        sel = [o for o in obs if bin_index(getattr(o, price), nbins) == b]
        n = len(sel)
        k = sum(1 for o in sel if o.outcome >= 0.5)
        lo, hi = wilson_interval(k, n) if n else (None, None)
        rows.append({
            "bin": b,
            "range": [round(b / nbins, 3), round((b + 1) / nbins, 3)],
            "n": n,
            "successes": k,
            "mean_price": (sum(getattr(o, price) for o in sel) / n) if n else None,
            "frequency": (k / n) if n else None,
            "wilson_lo": lo, "wilson_hi": hi,
            "bootstrap_lo": None, "bootstrap_hi": None,
            "bootstrap_draws_used": 0,
        })
    if not obs or draws <= 0:
        return rows

    # Per-block sufficient statistics, so a draw is a sum over blocks
    # rather than a pass over observations.
    blocks: dict[str, list[tuple[int, int]]] = {}
    for o in obs:
        b = bin_index(getattr(o, price), nbins)
        cell = blocks.setdefault(o.block, [(0, 0)] * nbins)
        k, n = cell[b]
        cell[b] = (k + (1 if o.outcome >= 0.5 else 0), n + 1)
    keys = sorted(blocks)
    if len(keys) < MIN_BOOTSTRAP_BLOCKS:
        for r in rows:
            r["bootstrap_blocks"] = len(keys)
        return rows
    rng = random.Random(seed)
    per_bin: list[list[float]] = [[] for _ in range(nbins)]
    for _ in range(draws):
        pick = [blocks[keys[rng.randrange(len(keys))]] for _ in keys]
        for b in range(nbins):
            k = sum(c[b][0] for c in pick)
            n = sum(c[b][1] for c in pick)
            if n:
                per_bin[b].append(k / n)
    for b in range(nbins):
        vals = per_bin[b]
        if len(vals) >= 20:          # too few usable draws is not an interval
            rows[b]["bootstrap_lo"] = _percentile(vals, BOOTSTRAP_ALPHA / 2)
            rows[b]["bootstrap_hi"] = _percentile(vals, 1 - BOOTSTRAP_ALPHA / 2)
        rows[b]["bootstrap_draws_used"] = len(vals)
        rows[b]["bootstrap_blocks"] = len(keys)
    return rows


def bootstrap_brier(obs: Sequence[Observation], price: str = "mid",
                    draws: int = BOOTSTRAP_DRAWS,
                    seed: int = BOOTSTRAP_SEED) -> tuple[float | None, float | None]:
    """Block bootstrap interval on the Brier score itself."""
    if not obs or draws <= 0:
        return None, None
    blocks: dict[str, list[float]] = {}
    for o in obs:
        blocks.setdefault(o.block, []).append((getattr(o, price) - o.outcome) ** 2)
    stats = {k: (sum(v), len(v)) for k, v in blocks.items()}
    keys = sorted(stats)
    if len(keys) < MIN_BOOTSTRAP_BLOCKS:
        return None, None
    rng = random.Random(seed)
    vals = []
    for _ in range(draws):
        s = n = 0.0
        for _ in keys:
            a, b = stats[keys[rng.randrange(len(keys))]]
            s += a
            n += b
        if n:
            vals.append(s / n)
    if len(vals) < 20:
        return None, None
    return (_percentile(vals, BOOTSTRAP_ALPHA / 2),
            _percentile(vals, 1 - BOOTSTRAP_ALPHA / 2))


def favourite_longshot(obs: Sequence[Observation], price: str,
                       nbins: int = RELIABILITY_BINS) -> list[dict]:
    """Realised frequency against the traded price, bin by bin.

    ``price`` is ``"bid"`` or ``"ask"`` and never ``"mid"``: the bias this
    measures is a statement about what someone paid or received, and
    nobody trades the mid. ``bias_cents`` is
    ``(frequency - mean price) * 100``, so a negative number means the
    side quoted at that price was dearer than it turned out to be worth.
    """
    rows = []
    for b in range(nbins):
        sel = [o for o in obs if bin_index(getattr(o, price), nbins) == b]
        n = len(sel)
        k = sum(1 for o in sel if o.outcome >= 0.5)
        mp = (sum(getattr(o, price) for o in sel) / n) if n else None
        freq = (k / n) if n else None
        lo, hi = wilson_interval(k, n) if n else (None, None)
        rows.append({
            "bin": b,
            "range": [round(b / nbins, 3), round((b + 1) / nbins, 3)],
            "n": n, "successes": k,
            "mean_price": mp, "frequency": freq,
            "bias_cents": (None if mp is None else round((freq - mp) * 100, 2)),
            # The spread is not decoration. A bin whose median spread is 85
            # cents is a bin of nominal quotes on near-empty books, and its
            # "bias" is mostly that fact. Reported rather than filtered on,
            # because choosing a spread cut-off is a judgement and hiding
            # the rows behind it would be making that judgement silently.
            "median_spread_cents": (
                round(_median([(o.ask - o.bid) * 100 for o in sel]), 1)
                if n else None),
            "wilson_lo": lo, "wilson_hi": hi,
        })
    return rows


def score_group(obs: Sequence[Observation], bootstrap: bool = True) -> dict:
    """Brier, log score and skill for one slice, against the 50/50 baseline."""
    ps = [o.mid for o in obs]
    ys = [o.outcome for o in obs]
    br = brier_score(ps, ys)
    lg, clipped = log_score(ps, ys)
    lo = hi = None
    if bootstrap and obs:
        lo, hi = bootstrap_brier(obs)
    return {
        "n": len(obs),
        # How many independent settlement days this slice is really made of.
        # 1,209 forecasts drawn from 4 settlement days is 4 observations of
        # the world, and the block count is what says so.
        "blocks": len({o.block for o in obs}),
        "brier": br,
        "brier_bootstrap_lo": lo,
        "brier_bootstrap_hi": hi,
        "log_score": lg,
        "log_clipped": clipped,
        "brier_skill_vs_5050": skill(br),
        "log_lift_vs_5050": None if lg is None else lg - BASELINE_LOG,
        "mean_mid": (sum(ps) / len(ps)) if ps else None,
        "base_rate": (sum(ys) / len(ys)) if ys else None,
        "median_spread_cents": (
            round(_median([(o.ask - o.bid) * 100 for o in obs]), 2)
            if obs else None),
        # Hours from the scored quote to settlement, NOT staleness. At the
        # 1 d horizon this sits between 24 and 48 by construction: the cut-off
        # is 24 h before settlement and the quote may be up to
        # MAX_QUOTE_AGE_HOURS older than the cut-off.
        "median_hours_before_settlement": (
            round(_median([o.quote_age_hours for o in obs]), 2)
            if obs else None),
    }


# --------------------------------------------------------------------------
# The join
# --------------------------------------------------------------------------

def _quote_from_row(venue: str, r: dict) -> tuple[float, float, float | None,
                                                  str, str] | None:
    """(bid, ask, liquidity, category, era) for the side the outcome scores,
    or None when the row carries no usable **two-sided** quote.

    Two-sidedness is a hard requirement on every venue that runs a book: a
    market with only one side quoted has not made a forecast this module
    can score, and its "mid" is not a price anyone offered. On the archive
    as it stands this rejects 233 market/horizon cells, all of them
    Polymarket rows with a missing ``bestBid`` or ``bestAsk`` (checked
    2026-09-11: no Polymarket row in the first 30 snapshots quotes a bid or
    ask of exactly zero -- the venue omits the field instead) plus Kalshi
    rows the loader already marks one-sided.

    Two-sidedness is **not** sufficient, and the tables say so rather than
    filtering further. In the 1 d sample the 189 forecasts whose ask is at
    or above 0.90 have a *median spread of 85 cents*: split them, and the
    79 with a spread of 10 cents or less settled YES 97.5% of the time
    against a mean ask of 0.985, while the 110 wider ones settled YES 44.5%
    of the time. The favourite-longshot table reports a median spread per
    bin for exactly this reason; a nominal ask on an empty book is a
    two-sided quote and still not a price.

    Manifold is the exception and is flagged as one: it publishes a single
    probability rather than a book, so its bid and ask are that number.
    """
    if venue == "kalshi":
        bid, ask = r.get("yes_bid"), r.get("yes_ask")
        if bid is None or ask is None or not r.get("two_sided"):
            return None
        return (bid, ask, r.get("open_interest"),
                str(r.get("category") or "unknown"), "")
    if venue == "polymarket":
        bid, ask = r.get("bestBid"), r.get("bestAsk")
        if bid is None or ask is None or bid <= 0.0 or ask <= 0.0:
            return None
        return bid, ask, r.get("liquidity"), "unknown", str(r.get("era") or "")
    if venue == "manifold":
        p = r.get("probability")
        if p is None:
            return None
        return p, p, r.get("totalLiquidity"), "unknown", ""
    if venue == "predictit":
        bid, ask = r.get("bestSellYesCost"), r.get("bestBuyYesCost")
        if bid is None or ask is None or bid <= 0.0 or ask <= 0.0:
            return None
        return bid, ask, None, "unknown", ""
    return None


_VENUE_KEY = {
    "kalshi": "ticker",
    "polymarket": "id",
    "manifold": "id",
    "predictit": "contract_id",
}


class CalibrationJoin:
    """Streaming join of settlements onto the archive's quote history.

    One pass over the snapshots, in any order. For each settled market and
    horizon only the best candidate quote so far is retained, so memory is
    O(settled markets x horizons) and does not grow with the archive.
    """

    def __init__(self, settlements: SettlementSet,
                 horizons: Sequence[tuple[str, float]] = HORIZONS,
                 max_quote_age_hours: float = MAX_QUOTE_AGE_HOURS):
        self.settlements = settlements
        self.horizons = tuple(horizons)
        self.max_age = timedelta(hours=max_quote_age_hours)
        self.snapshots_seen = 0
        self.first_snapshot: datetime | None = None
        self.last_snapshot: datetime | None = None
        #: {(venue, key, horizon): (quote_t, bid, ask, liquidity, category, era)}
        self._best: dict[tuple[str, str, str], tuple] = {}
        #: Same cells, ignoring the age cap. The difference between the two
        #: is the number of forecasts this module refused to invent out of a
        #: stale quote, and it is reported rather than swallowed.
        self._best_any: dict[tuple[str, str, str], datetime] = {}
        #: Cells whose only in-window quote was one-sided. Reported, because
        #: silently dropping them would make the sample look cleaner than
        #: the archive is.
        self._one_sided: set[tuple[str, str, str]] = set()
        #: settled markets that were quoted at least once, at any time
        self._quoted_ever: set[tuple[str, str]] = set()
        self._cuts: dict[tuple[str, str], list[tuple[str, datetime, datetime]]] = {}
        for venue, by_key in settlements.by_venue.items():
            for key, st in by_key.items():
                self._cuts[(venue, key)] = [
                    (label, st.settled_at - timedelta(days=days),
                     st.settled_at - timedelta(days=days) - self.max_age)
                    for label, days in self.horizons]

    def observe(self, snap: Snapshot) -> None:
        self.snapshots_seen += 1
        t = snap.t
        if self.first_snapshot is None or t < self.first_snapshot:
            self.first_snapshot = t
        if self.last_snapshot is None or t > self.last_snapshot:
            self.last_snapshot = t
        for venue, by_key in self.settlements.by_venue.items():
            if not by_key:
                continue
            keyfield = _VENUE_KEY[venue]
            for r in snap.venues.get(venue, []):
                raw = r.get(keyfield)
                if raw is None:
                    continue
                key = str(raw)
                if key not in by_key:
                    continue
                self._quoted_ever.add((venue, key))
                q = _quote_from_row(venue, r)
                for label, cut, floor in self._cuts[(venue, key)]:
                    if t > cut:
                        continue
                    cell = (venue, key, label)
                    if q is None:
                        if floor <= t:
                            self._one_sided.add(cell)
                        continue
                    seen = self._best_any.get(cell)
                    if seen is None or t > seen:
                        self._best_any[cell] = t
                    if t < floor:
                        continue
                    prev = self._best.get(cell)
                    if prev is None or t > prev[0]:
                        self._best[cell] = (t, q[0], q[1], q[2], q[3], q[4])

    def observations(self) -> list[Observation]:
        out: list[Observation] = []
        for (venue, key, label), (t, bid, ask, liq, cat, era) in sorted(
                self._best.items()):
            st = self.settlements.by_venue[venue][key]
            mid = (bid + ask) / 2.0
            out.append(Observation(
                venue=venue, key=key, horizon=label, outcome=st.outcome,
                mid=mid, bid=bid, ask=ask, quote_t=t,
                quote_age_hours=round(
                    (st.settled_at - t).total_seconds() / 3600.0, 3),
                settled_at=st.settled_at, liquidity=liq,
                liquidity_band=liquidity_band(liq), category=cat, era=era,
                block=st.block, inferred=st.inferred, question=st.question))
        return out

    # ---------------------------------------------------------------- report

    def report(self) -> dict:
        obs = self.observations()
        headline = [o for o in obs if not o.inferred]
        rep: dict = {
            "settlements_read": self.settlements.total(),
            "settlement_files": self.settlements.files_read,
            "settlement_roots": self.settlements.roots,
            "settlements_by_venue": {v: len(k) for v, k
                                     in sorted(self.settlements.by_venue.items())},
            "settlements_excluded": {v: dict(sorted(d.items())) for v, d
                                     in sorted(self.settlements.excluded.items())},
            "settled_markets_quoted_in_archive": len(self._quoted_ever),
            "snapshots_seen": self.snapshots_seen,
            "horizons": [{"label": l, "days": d} for l, d in self.horizons],
            "max_quote_age_hours": MAX_QUOTE_AGE_HOURS,
            "baseline": {"p": BASELINE_P, "brier": BASELINE_BRIER,
                         "log_score": round(BASELINE_LOG, 6)},
            "liquidity_field": dict(LIQUIDITY_FIELD),
            "observations": len(obs),
            "observations_rejected_stale": len(self._best_any) - len(self._best),
            "observations_rejected_one_sided": len(
                self._one_sided - set(self._best)),
            "one_sided_rule": (
                "a market/horizon cell whose only in-window quote had no bid "
                "or no ask is reported unscored: a one-sided book has not "
                "made a forecast, and its mid is not a price"),
            "stale_rule": (
                f"a market/horizon cell whose newest quote at or before the "
                f"cut-off was more than {MAX_QUOTE_AGE_HOURS:g} h older than "
                f"the cut-off is reported unscored rather than scored on a "
                f"stale price"),
            "observations_headline": len(headline),
            "inferred_excluded_from_headline": len(obs) - len(headline),
            "empty": not headline,
            "note": "" if headline else EMPTY_NOTE,
            "by_horizon": {}, "by_venue_horizon": {}, "by_category": {},
            "by_liquidity": {}, "by_era": {},
            "reliability": {}, "favourite_longshot": {},
            "inferred": {},
        }
        if not obs:
            return rep

        by_h = {l: [o for o in headline if o.horizon == l]
                for l, _ in self.horizons}
        rep["by_horizon"] = {l: score_group(v) for l, v in by_h.items()}
        for l, v in by_h.items():
            rep["by_horizon"][l]["coverage"] = {
                "settled_markets_scored": len({o.key for o in v}),
                "why_empty": ("" if v else self._why_empty(l)),
            }

        for venue in HEADLINE_VENUES:
            for l, _ in self.horizons:
                sel = [o for o in headline
                       if o.venue == venue and o.horizon == l]
                if sel:
                    rep["by_venue_horizon"][f"{venue}|{l}"] = score_group(sel)

        # The headline horizon is the shortest one that has any data: with
        # a three-week archive that is 1 d, and the report says which it is
        # rather than assuming.
        head_label = next((l for l, _ in self.horizons if by_h.get(l)), None)
        rep["headline_horizon"] = head_label
        head = by_h.get(head_label, []) if head_label else []
        rep["headline"] = score_group(head) if head else None

        if head:
            for cat in sorted({o.category for o in head}):
                rep["by_category"][cat] = score_group(
                    [o for o in head if o.category == cat], bootstrap=False)
            for band in sorted({o.liquidity_band for o in head}):
                rep["by_liquidity"][band] = score_group(
                    [o for o in head if o.liquidity_band == band],
                    bootstrap=False)
            for era in sorted({o.era for o in head if o.era}):
                rep["by_era"][era] = score_group(
                    [o for o in head if o.era == era], bootstrap=False)
            rep["reliability"]["all"] = reliability(head)
            for venue in sorted({o.venue for o in head}):
                sel = [o for o in head if o.venue == venue]
                if len(sel) >= 1:
                    rep["reliability"][venue] = reliability(sel)
            rep["favourite_longshot"] = {
                "bid": favourite_longshot(head, "bid"),
                "ask": favourite_longshot(head, "ask"),
                "note": ("Manifold quotes a single probability rather than a "
                         "book, so its bid and ask columns carry the same "
                         "number; the venue split says how much of each row "
                         "that is."),
                "venues": sorted({o.venue for o in head}),
                "venue_counts": {v: sum(1 for o in head if o.venue == v)
                                 for v in sorted({o.venue for o in head})},
            }
            # What the sample is made of. A Brier score means nothing until
            # the reader knows it came from four settlement days of mostly
            # one venue's sports markets, so the composition ships with it.
            days: dict[str, int] = {}
            for o in head:
                days[o.block] = days.get(o.block, 0) + 1
            rep["composition"] = {
                "horizon": head_label,
                "n": len(head),
                "by_venue": {v: sum(1 for o in head if o.venue == v)
                             for v in sorted({o.venue for o in head})},
                "by_era": {e: sum(1 for o in head if o.era == e)
                           for e in sorted({o.era for o in head if o.era})},
                "settlement_blocks": len(days),
                "largest_blocks": [{"block": k, "n": v} for k, v in
                                   sorted(days.items(),
                                          key=lambda kv: (-kv[1], kv[0]))[:8]],
            }
            rep["mean_mid_by_outcome"] = {
                "settled_yes": round(
                    sum(o.mid for o in head if o.outcome >= 0.5)
                    / max(1, sum(1 for o in head if o.outcome >= 0.5)), 4),
                "settled_no": round(
                    sum(o.mid for o in head if o.outcome < 0.5)
                    / max(1, sum(1 for o in head if o.outcome < 0.5)), 4),
                "note": ("A sanity check on the outcome join, not a result: "
                         "if the quote were aligned to the wrong side of the "
                         "market these two would be the wrong way round."),
            }

        inf = [o for o in obs if o.inferred]
        if inf:
            rep["inferred"] = {
                "n": len(inf),
                "venues": sorted({o.venue for o in inf}),
                "by_horizon": {l: score_group(
                    [o for o in inf if o.horizon == l], bootstrap=False)
                    for l, _ in self.horizons
                    if any(o.horizon == l for o in inf)},
                "note": ("PredictIt outcomes are inferred from the last "
                         "trade of a contract that left the public feed, "
                         "not observed. These scores are reported so the "
                         "inference can be judged, and are excluded from "
                         "every headline number."),
            }
        return rep

    def _why_empty(self, label: str) -> str:
        days = dict(self.horizons)[label]
        if self.first_snapshot is None:
            return "no snapshots were replayed"
        earliest = self.first_snapshot + timedelta(days=days)
        return (f"no settled market resolved on or after "
                f"{earliest.strftime('%Y-%m-%dT%H:%M:%SZ')}, which is the "
                f"earliest settlement this archive can price {label} ahead "
                f"(it opens {self.first_snapshot.strftime('%Y-%m-%d')}).")


def empty_report(reason: str = "") -> dict:
    """The report shape when there is nothing to join at all."""
    j = CalibrationJoin(SettlementSet())
    rep = j.report()
    if reason:
        rep["note"] = reason
    return rep


def write_observations(obs: Iterable[Observation], path: str | Path) -> Path:
    """One CSV row per scored forecast, so the tables can be re-derived."""
    import csv
    cols = ("venue", "key", "horizon", "outcome", "mid", "bid", "ask",
            "quote_t", "quote_age_hours", "settled_at", "liquidity",
            "liquidity_band", "category", "era", "block", "inferred")
    p = Path(path)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(cols)
        for o in obs:
            w.writerow([
                o.venue, o.key, o.horizon, int(o.outcome), f"{o.mid:.6f}",
                f"{o.bid:.6f}", f"{o.ask:.6f}",
                o.quote_t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                f"{o.quote_age_hours:.3f}",
                o.settled_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "" if o.liquidity is None else f"{o.liquidity:.4f}",
                o.liquidity_band, o.category, o.era, o.block,
                int(o.inferred)])
    return p
