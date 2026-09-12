# prediction-markets-lab

Are quoted event probabilities coherent, and when they disagree, who is
right? A measurement engine for prediction markets, built on the rule
that made the sibling projects work: record first, screen honestly,
and let weeks of data draw the conclusions.

The repo records its own data with no server anywhere: a GitHub Actions
cron snapshots four venues' public APIs and commits the result. The cron
is scheduled every two hours; across every interval in the archive
the realised cadence is a median 3.3 h with a maximum gap of 12.6 h
(2026-08-27 and 08-28 have two snapshots each), because hosted schedulers
delay runs under load. Every run succeeded, so the gaps are scheduler
delay, not failures. The history accumulates from the day the repo went
live, so every later study has an archive it can replay.

## Venues

| venue | recorded per snapshot (recorder v2) | source |
|---|---|---|
| Kalshi | every open non-Sports market plus the 3,000 highest-open-interest Sports markets, with event metadata. On the newest recorded snapshot (2026-09-11T20:03Z) that swept 135,289 open markets, 81,664 of them Sports, and kept 56,625 across 7,266 events | official public API v2 |
| Polymarket | top 1,000 by `liquidityNum`, sorted client-side, rows already past their `endDate` dropped | gamma API |
| PredictIt | full catalog (about 190 markets, about 590 contracts) | official API |
| Manifold | 1,000 most liquid open binaries (`search-markets?sort=liquidity`) | official API |

No keys, no scraping; snapshots are trimmed to the fields the studies
need. Every Kalshi figure in that row is the recorder's own tally, stored
in the snapshot it describes under `meta.kalshi` (`swept`, `kept`,
`events`, `by_category`), so it can be read back out of the archive
rather than taken on trust — and it moves as the venue's catalog moves,
which is why it is quoted against a named snapshot instead of as a
standing fact.

Recorder v1 (2026-08-23 to the merge of this branch) recorded the first
2,000 Kalshi events (about 14,000 markets, dominated by the two midterm
ladder families), Polymarket as served, and Manifold's 1,000 newest
markets; those blobs are kept unchanged and load through the same loader
(see "Provenance and corrections").

## Storage

Snapshots live in two places and history is never rewritten:

- `data/` on `main`: the first 117 snapshots (2026-08-23 to 2026-09-11,
  about 71 MB, recorder v1). They stay where they are.
- the orphan `data` branch: every snapshot from recorder v2 onward under
  `data/YYYYMMDD/HHMMZ.json.gz`, a `manifest.json` with the sha256 and
  size of every blob plus an archive identity hash, and `settlements/`
  written by the daily settlement job. The recorder checks this branch
  out as a partial clone and appends one blob per run, so a run costs the
  same whether the branch holds ten snapshots or ten thousand.

`pmlab.archive.load_snapshot(path)` reads either schema and either
Polymarket era into one flat, float-typed row list per venue;
`pmlab.archive.snapshot_paths("data", "archive/data")` walks both roots.

## Settlements

`settle.py` runs daily (`.github/workflows/settle.yml`) and follows every
market the archive has ever quoted to its outcome:

- Kalshi: `GET /markets?status=settled&min_settled_ts=...`, kept for
  recorded tickers, deduplicated by ticker and settlement time, with a
  one-time backfill from 2026-08-23.
- Polymarket: every recorded id re-polled through the gamma API with
  `closed=true` (the bare id query returns only markets still open),
  storing `umaResolutionStatus`, `outcomePrices` and `closedTime`.
- Manifold: `GET /v0/market/{id}` for ids past their close time, storing
  `isResolved`, `resolution`, `resolutionTime`, `resolutionProbability`.
- PredictIt: the public feed carries open markets only, so a contract
  that leaves the feed is recorded from its last trade and flagged
  `"inferred": true`; inferred outcomes are excluded from headline tables.

## Phase 1 (live): coherence screening

`screen.py` checks the constraints that need no model, only logic:

1. **Complement.** Buying YES and NO at the ask must cost at least $1.
   Reported gross and net of the venue fee, because the first lesson of
   screening real markets is that gross violations are usually the
   spread wearing a costume. On Kalshi this check cannot fire: the
   venue's NO quotes are the mirror image of the YES book (NO ask equals
   1 minus YES bid on every two-sided book in every snapshot recorded so
   far), so YES ask plus NO ask equals 1 plus the spread by construction.
   The identity is therefore tracked as a data-quality invariant (a test
   fails if it ever breaks), not reported as a result. The complement
   screen proper belongs to the venues where it is not tautological:
   Polymarket Yes/No books and PredictIt YES/NO pairs, with their fees.
2. **Bucket sums.** For a mutually exclusive event, YES asks summing
   below $1 is a candidate underround. Candidate, and the output says
   so loudly: the survivors on the first snapshot (next pope, 51st
   state) are exactly the open-universe events whose listed buckets are
   not exhaustive, the classic trap this check exists to expose rather
   than fall into.
3. **Ladder monotonicity.** Threshold markets on one variable must
   price P(>= s) decreasing in s; a higher strike bidding over a lower
   strike's ask is incoherence beyond the spread. The "44 ladders, zero
   inversions" figure previously quoted here was measured once, on
   2026-08-23, with a title regex that matched about 3% of markets. It
   was a coverage artifact: the parser in `pmlab/ladders.py` covers the
   families that actually appear in the archive (`Above NK`, `Above N%`,
   `At least N%`, `Above NM`, `Above N million`, `Above N billion`,
   `N or more`, `At or above N`, and the party margin-of-victory
   `Republicans, N+ pts`) and reads the venue's structured
   `strike_type`/`floor_strike`/`cap_strike` fields wherever recorder v2
   captured them. Every ladder number below is regenerated by CI and
   dated.

The interesting output is not any single hit; it is the time series of
these counts as snapshots accumulate: how often does anything survive
honest fee accounting, and for how long? That series is
[`results/`](results/README.md), produced by `python -m pmlab.replay`;
`screen.py` is a single-snapshot view over the same modules.

## Phase 2 (live): the archive, replayed

`python -m pmlab.replay` runs every screen over every snapshot and writes
[`results/`](results/README.md): `timeseries.csv` (one row per snapshot),
`summary.json`, generated Markdown tables, and an SVG per screen. CI
regenerates all of it on every push and daily after the recorder, and
`scripts/check_readme.py` fails the build if a number in this file
disagrees with `results/summary.json` — which is exactly how "44 ladders"
went stale unnoticed. Every figure below is regenerated, not typed.

The replay re-reads the whole archive every run, and the archive only
grows, so `--cache` makes it incremental: a snapshot's coherence counts
are a function of that snapshot's bytes alone, and a blob whose sha256
has not moved is not screened again. On a 123-snapshot archive that is a
median 40 s down to 12 s (`scripts/bench_replay.py --end-to-end`, five
interleaved runs each, page cache warmed first; the no-cache runs spread
34-41 s and the cached ones 11-14 s on this machine), with
`timeseries.csv`, `summary.json` and `calibration.csv` byte-identical to a
cold run — which is the only claim worth making about a cache, and
`tests/test_incremental.py` pins it in both directions. The cache discards
itself whenever any module in `pmlab/` changes, so it can never serve a
number produced by code that no longer exists.

The benchmark interleaves the two configurations and reads all 88 MB once
before timing starts, because the obvious way to measure a cache flatters
it twice over: the first run of a pair pays for a cold page cache that the
second does not, and the first `--cache` run is the one that *populates*
the cache and has no hits to serve. Timed that way the same code looks
about 9x faster. It is 3x. An identical no-cache replay varies by about a
fifth run to run here, so what is quoted is a median with its spread.

What it deliberately does **not** skip is reading the blob. The
settlement join is not a function of one snapshot — a market settling
tomorrow is scored against a quote recorded weeks ago — so every blob is
still decoded and only the rows the join can use are coerced. On the
newest recorder-v2 snapshot (56,625 markets, 2.86 MB gzipped) the same
benchmark splits that into 0.74 s to load, 0.43 s to screen and 0.34 s to
decode alone; the cache removes the screen column and the decode is the
floor, because a blob's identity is its bytes. That floor is the part
that still grows with the archive; the next step, when the job approaches
its ten-minute budget again, is a per-blob quote index written once and
read instead of the blob.

**Archive replayed:** 125 <!-- results:archive.snapshots --> snapshots
from 2026-08-23 to 2026-09-11 — 19.9 <!-- results:archive.days_spanned -->
days, realised cadence median 3.3 <!-- results:archive.median_gap_hours -->
h — of which 117 <!-- results:archive.schema1_snapshots --> come from
recorder v1 and 8 <!-- results:archive.schema2_snapshots --> from v2.

### Ladders

The two recorders see different universes: v1 stopped at 2,000 events
(about 14,000 markets, dominated by the two midterm ladder families), v2
sweeps the whole open catalog (about 56,000). Pooling them counts two
different experiments as one, so the headline is split.

| recorder | snapshots | adjacent strike pairs tested | inversions gross | net of fee |
|---|---|---|---|---|
| v1 (2,000-event cap) | 117 <!-- results:ladders.by_recorder.schema1.snapshots --> | 804,708 <!-- results:ladders.by_recorder.schema1.adjacent_pairs --> | 291 <!-- results:ladders.by_recorder.schema1.inversions_gross --> | 0 <!-- results:ladders.by_recorder.schema1.inversions_net --> |
| v2 (full catalog) | 8 <!-- results:ladders.by_recorder.schema2.snapshots --> | 201,193 <!-- results:ladders.by_recorder.schema2.adjacent_pairs --> | 29 <!-- results:ladders.by_recorder.schema2.inversions_gross --> | 3 <!-- results:ladders.by_recorder.schema2.inversions_net --> |

An inversion is a higher strike bid over a lower strike's ask: sell the
higher, buy the lower, and the pair pays whatever happens, because the
higher strike cannot settle YES while the lower settles NO. Gross counts
the quote; net charges the venue's taker fee on both legs with the
venue's rounding — ceil to the cent, **per order**, so the smallest fee
on any risky contract is a full cent and a two-legged trade starts two
cents behind. The old screen charged the unrounded `0.07·p·(1-p)`, which
at a one-cent contract is fourteen times too little; that single
correction is the whole difference between "a one-cent inversion
survives" and "it does not".

Over the recorder-v1 slice the answer is a clean negative: not one
of the 291 <!-- results:ladders.by_recorder.schema1.inversions_gross -->
gross inversions was wider than three cents, against the two to four
cents of fee the two legs cost (a taker leg can never cost more than two
cents, and never less than one), and they were not spread across the
catalog either — the archive's
320 <!-- results:ladders.inversions_gross_total --> gross inversions fall
in 28 <!-- results:ladders.inversion_events --> events, overwhelmingly the
long-dated `KXFEDFUNDSYEAR-3x` and `KXUSCPIYEAR` ladders that settle years
out and that nobody is minding.

The v2 slice is 8 <!-- results:ladders.by_recorder.schema2.snapshots -->
snapshots so far and is reported as the preliminary thing it is, but it is
already more interesting:
3 <!-- results:ladders.inversions_net_total --> inversions survive the fee,
all in 1 <!-- results:ladders.net_inversion_events --> event —
`KXINXMINY-01JAN2027`, the "minimum S&P 500 value by Jan 1 2027" ladder,
where the bid on P(min ≤ 6,000.01) stood *above* the ask on
P(min ≤ 6,100.01) even though the first outcome implies the second. It
shows up in 3 <!-- results:ladders.snapshots_with_net_inversion --> of
those snapshots and not in the ones after them, 0.4c to 1.0c net: three
consecutive readings spanning under three hours on one day is an
observation, not a rate, and it needs weeks of v2 recording before it is
a result. What it is not is invisible — it is in the catalog at all only
because v2 lifted the 2,000-event cap. It also sits in exactly the family
whose reduced fee multiplier this repo has not read yet: if a reduced rate
applies to the `KXINX*` series, the net edge is **larger** than reported
here, not smaller.

Two false positives were removed before publishing these counts, both
worth naming because the structured fields invited them: `KXNFLSPREAD`
lists both teams' spreads in one event with `strike_type="greater"` on
every market, and `KXSTARSHIPSPACE` lists "exactly 5", "exactly 6" as
`strike_type="less"` with `floor_strike == cap_strike` — byte-identical to
a real "6,300 or below" CDF rung. Grouping on
`(event_ticker, strike_type)` alone read a 35c and a 46c "arbitrage" out
of markets that can both settle YES. Rungs now also have to agree on the
shape of their sub-title, and a rung whose sub-title is a bare number is
refused.

At mids rather than at the touch, the same ladders imply negative
probability mass between adjacent strikes
22,654 <!-- results:ladders.negative_mass_gross_total --> times. That is a
statement about where quotes are marked, not a trade, and the two numbers
are kept apart on purpose.

### Complement

Kalshi is not screened, because the screen cannot fire there:
`no_ask == 1 - yes_bid` held on
1,849,537 <!-- results:kalshi_identity.books_checked_total --> of
1,849,537 <!-- results:kalshi_identity.books_checked_total --> two-sided
books, 0 <!-- results:kalshi_identity.deviations_total --> deviations, so
YES ask + NO ask is 1 + spread by construction. The replay asserts the
identity and fails the build if it ever breaks — a venue changing its data
model is a thing to look at, not a result to publish.

Where the screen can fire:
61,208 <!-- results:predictit_complement.pairs_total --> PredictIt YES/NO
ask pairs give 0 <!-- results:predictit_complement.gross_total -->
violations gross. 116,674 <!-- results:polymarket_complement.pairs_total -->
Polymarket quoted outcome pairs give
43 <!-- results:polymarket_complement.gross_total -->, and all
43 <!-- results:polymarket_complement.gross_string_sorted_era --> of them
are inside the string-sorted era, against
0 <!-- results:polymarket_complement.gross_numeric_era --> in the
57 <!-- results:polymarket_complement.snapshots_numeric_era --> clean
snapshots. The incoherent quotes are in the thin, often already-expired
rows the recorder's broken sort surfaced, which makes that a finding about
this repo rather than about Polymarket.

### Bucket sums

A median of 228 <!-- results:buckets.screened_median_per_snapshot -->
mutually exclusive events per snapshot are fully quoted;
20 <!-- results:buckets.candidates_gross_median --> of them sum below a
dollar gross and 8 <!-- results:buckets.candidates_net_median --> net of
fees. The same tickers recur in every snapshot — next pope, 51st state,
party nominations, Moldovan president — which is the open-universe trap
this screen exists to name rather than fall into: the missing "someone
else" bucket is the missing mass.

### The one-line answer, dated 2026-09-11

Over 19.9 <!-- results:archive.days_spanned --> days and
125 <!-- results:archive.snapshots --> snapshots —
1,005,901 <!-- results:ladders.adjacent_pairs_total --> adjacent strike
pairs, 61,208 <!-- results:predictit_complement.pairs_total --> PredictIt
pairs, 116,674 <!-- results:polymarket_complement.pairs_total -->
Polymarket pairs, 33,779 <!-- results:buckets.screened_total --> screened
bucket-sum events — honest fee accounting erases every coherence violation
the screens can find, with one exception, and the exception appeared the
moment the recorder stopped truncating the catalog:
`KXINXMINY-01JAN2027`, the S&P-500-minimum ladder, inverted by up to
1.0 <!-- results:ladders.worst_net_inversion.net_edge_cents --> cent net
of fee in all 8 <!-- results:ladders.by_recorder.schema2.snapshots -->
recorder-v2 snapshots recorded so far. Both halves of that sentence get
published at the same size.

### Cross-venue basis

`pmlab/basis.py` prices the same event on two venues and reports the
fee-adjusted basis distribution and its half-life. The pairs come from
[`events.yaml`](events.yaml), which is written by hand under one rule:

> **Identical entity and identical deadline on both venues**, read off
> both venues' rules pages by a person. No fuzzy matching.

That rule is not fastidiousness, it is what the data forces. On the
archive's first snapshot, exact title matching across every venue pair
yields zero pairs; token-Jaccard at 0.75 yields one, and it is wrong
(Polymarket's "next cabinet member to leave" against Kalshi's "first
cabinet member to leave"); a PredictIt/Kalshi keyword overlap yields 28
of 187 and matches party-wins markets against margin-of-victory ladders.
A wrong pair does not produce a small error, it produces a basis that is
entirely an artefact.

So every pair carries `verified: true|false`, **unverified pairs are
counted and never priced**, and a pair claiming verification without a
`checked_on` date is rejected by the loader. The file ships as a skeleton
of 4 <!-- results:basis.pairs_total --> example pairs, of which
0 <!-- results:basis.pairs_verified --> are verified today. Each one
names the specific thing a person has to go and check, and every one of
them is there precisely because it looks like a pair and is not yet known
to be one: "shutdown **on** Oct 1" against "shutdown **by** Oct 1"; a
threshold on the fed funds level against a statement about the change; a
Nobel prize announced in October against a Kalshi market that trades
until December. Manifold legs are rejected outright: it is play money, so
a dollar basis against it is not a dollar.

Two things the file learned the hard way, because an unverified pair is
never priced and so nothing ever failed on either. Its Nobel pair named a
Kalshi ticker that had been *guessed* at (`KXNOBELPEACE-27-EMUS`) and
appears in no recorded snapshot; the real one, read out of the
2026-09-11T20:03Z catalog, is `KXNOBELPEACE-26-ELO`. And its recession
pair carried the literal string `TODO-find-the-nber-market-id` where a
Polymarket market id belongs — no recorded Polymarket or PredictIt row
settles on the NBER announcement, so that pair is dropped and the reason
is written where it stood. `pmlab/basis.py` now refuses any leg key
containing `TODO`/`TBD`/`FIXME`, so a placeholder cannot sit inside the
count again.

Until a pair is verified, [`results/README.md`](results/README.md) prints
an empty basis table with that reason attached. That is the honest output,
and it is the current one.

## Phase 3 (live): calibration

Every screen above asks whether a set of prices is *coherent*. Calibration
asks whether it was *right*, which needs outcomes, which is why it could
not exist until `settle.py` started following recorded markets to their
settlement. `pmlab/calibration.py` runs inside the same replay pass and
writes its tables into [`results/README.md`](results/README.md) and its
per-forecast rows into `results/calibration.csv`.

**The join.** For each settled market and each horizon H - 1 day, 1 week,
1 month, 2 months - the scored quote is the last one recorded at or
before `settled_at - H`, and it is used only if it is no more than 24 h
older than that cut-off. The age cap is the part that makes the rest
trustworthy: without it a market that settled on 2026-09-10 and was last
quoted on 2026-08-23 would be scored as a one-day-ahead forecast when it
is an eighteen-day-ahead one, and the 1 d column would quietly fill with
stale prices. 24 h is just under twice the worst gap the recorder has
actually produced against its 3.3 h median, so a normally-quoted market
always has a usable quote and a market the recorder missed is reported
missing rather than invented. A horizon longer than the archive is
therefore empty *by construction*, and the table says which date would
fill it.

**What is scored.** Brier score and log score on the mid against a 50/50
baseline (Brier 0.25, log -0.6931), with the skill score beside them;
reliability curves in ten bins, each carrying both a Wilson interval and
a block-bootstrap interval over (venue, settlement day) blocks; and
favourite-longshot bias measured **separately on the bid and on the ask**,
never on the mid, because a longshot buyer pays the ask and a favourite
seller receives the bid while nobody trades the mid. Sliced by venue,
category, horizon, liquidity band and Polymarket recorder era.

**What it refuses to do.** A stale quote is reported unscored, not
scored. A one-sided book is reported unscored, because its mid is not a
price. Below three settlement-day blocks no bootstrap interval is
reported at all, because resampling two blocks describes the block count
rather than the data. Every refusal is counted in the output rather than
quietly dropped, and each table carries a `blocks` column next to its
`n`, because a thousand forecasts spread over four settlement days is
four observations of the world wearing a large `n`. A wide two-sided book is
*not* refused, but every favourite-longshot bin reports its median spread,
because a nominal ask sitting on an empty book is a two-sided quote and
still not a price. PredictIt is joined and reported but never enters a
headline number: the public feed carries open markets only, so its
outcomes are *inferred* from the last trade of a contract that vanished,
and scoring a forecast against a guess is not a measurement.

**Coverage today.** 38,659 <!-- results:calibration.settlements_read -->
settled markets have been captured, and
4,774 <!-- results:calibration.observations_headline --> market/horizon
cells have both an outcome and a usable pre-settlement quote; another
16,204 <!-- results:calibration.observations_rejected_stale --> were
refused for a stale quote and
1024 <!-- results:calibration.observations_rejected_one_sided --> for a
one-sided book. The scores themselves live in
[`results/README.md`](results/README.md) with their composition table
attached, and they should be read with it: this is not a random sample of
any venue's catalog, it is the set of markets that happened to resolve
inside a three-week recording window, which skews hard towards short-dated
sports and towards whatever the recorder's Polymarket slice held at the
time. The sample gets less strange every week the cron runs.

**The schedule.** Polymarket settles first and in volume: of the 1,000
rows in the newest recorded snapshot (2026-09-11T20:03Z), 471 end before
2026-11-04 and 300 end in September, so the first table with a large `n`
spread across many settlement days is an autumn 2026 table. That count is
of one snapshot's slice, not of the archive: the recorder keeps the top
1,000 by liquidity and the slice turns over, so across all 123 snapshots
35,996 distinct Polymarket ids have been seen.

Kalshi arrives later than the midterms suggest. The
recorded Kalshi election markets are the `KXMIDTERMMOV` margin-of-victory
and `KXMIDTERMVOTETURN` turnout ladders, and they settle on **certified**
results, so their outcomes land in December 2026 and January 2027 rather
than on election night; the per-race winner markets that do settle on
media calls were absent from recorder v1 entirely because of its
2,000-event cap, and enter the archive only from recorder v2 onward.
Manifold resolves continuously but is play money. So the table is rebuilt
on every run and gets its first serious Kalshi block over the winter.

## Later (undecided): does sentiment lead repricing?

Score public news flow (headline feeds, statement diffs for scheduled
events like FOMC) and test, walk-forward and out of sample, whether
sentiment shifts lead prediction-market price moves or lag them. The
recorder's timestamps make the lead-lag question answerable; nothing
gets reported in-sample. This one is deliberately unnumbered: it is the
weakest idea in this README, and the honest options are to do it properly
or to strike it - a decision to make once the winter calibration tables
are in, not before.

## Phase 4 (planned): model vs market on financial events

Kalshi lists range markets on equity indexes (KXINXY, KXINXDIRY and the
daily KXNASDAQ100U family are in the archive). Recorder v1 captured no BTC
range series at all — across all 117 v1 snapshots the only BTC ticker is
`KXTREASBUYBTC`, a custom-strike market, because the range series sat
beyond its 2,000-event cap. Lifting the cap fixed that: the newest v2
snapshot carries 21 series with BTC in the ticker, 13 of them with a
numeric strike type, including `KXBTC` (180 markets, mostly `between`
ranges) and `KXBTCD` (180 threshold markets). This phase now has both
legs of its comparison in the archive.

A calibrated options surface implies
risk-neutral probabilities for those exact events
([neural-options-lab](https://github.com/Ronak-Mahajan/neural-options-lab)
calibrates rough Bergomi with jumps to Deribit's BTC surface). The gap
between model probability and market price is risk premium plus
frictions, not free money; the study is its structure and stability.

## Provenance and corrections

- History was rewritten on 2026-08-31: the code and the first 65
  snapshots were bulk-added in one commit at that time, and the branch
  now shows one commit per snapshot, so per-snapshot commit timestamps
  before 2026-08-31 are reconstructed rather than original. The first
  seven snapshots on 2026-08-23 predate the first Actions run and were
  recorded locally. Snapshot content carries its own `t` timestamp and
  was not altered. History will not be rewritten again; new data goes to
  the `data` branch with a per-blob sha256 manifest.
- Polymarket rows from 2026-08-23 through the 2026-09-01T16:44Z snapshot
  are sorted by `liquidity` as a string (the venue served the field as
  text and recorder v1 trusted the server order): median liquidity about
  $99, 12% of rows already past their end date. The loader tags those
  rows `era="string_sorted"`; the blobs are kept as recorded.
- Recorder v1 stopped after 10 pages of 200 Kalshi events, so every v1
  snapshot holds exactly 2,000 events and the per-race 2026 winner
  series (for example KXHOUSE*) are absent from them. Recorder v2 sweeps
  the full open catalog.
- Manifold under recorder v1 was the 1,000 most recently created
  markets, not the most liquid; corrected in v2.
- Recorder v1 dropped Kalshi markets with no bid and no ask, so an event
  in a v1 snapshot may be missing buckets that were listed but unquoted.
  The bucket screen requires a live ask on every recorded bucket, which
  cannot see a bucket that was never recorded, so v1 bucket counts are an
  upper bound. Recorder v2 keeps unquoted markets with a `quoted` flag and
  the screen then skips the event outright.
- The Polymarket complement screen is run on the venue's quoted outcome
  pair, not on two asks: recorder v1 and v2 store one token's top of book,
  so the complementary token's ask is not in the archive. Assuming
  `no_ask == 1 - yes_bid` there would import exactly the tautology that
  disqualifies the Kalshi screen, so the number is reported as quote
  coherence, never as a demonstrated trade.
- The calibration sample is not a sample of any venue's catalog. It is
  the set of recorded markets that resolved inside the recording window,
  so it over-represents short-dated sports and, on Polymarket, the
  string-sorted era described above. `results/README.md` prints the
  venue, era and settlement-day composition directly above the scores,
  and the scores should not be quoted without it.
- PredictIt calibration numbers are computed from *inferred* outcomes
  (the contract left the public feed and its last trade is read as the
  answer) and are excluded from every headline table. They are published
  so the inference can be judged, not so it can be cited.
- Every number in this README is dated. Numbers a script produces are
  tagged `<!-- results:key -->` and checked against `results/summary.json`
  by `scripts/check_readme.py` in CI; a tagged number is never edited by
  hand.

## Run it

```
python record.py                      # one snapshot into data/
python record.py --out archive/data   # the data-branch layout used by CI
python settle.py --archive archive --snapshots data
python screen.py                      # coherence report on the newest snapshot
python -m pmlab.replay                # every screen over every snapshot -> results/
python -m pmlab.replay --roots data --no-plots    # no matplotlib needed
python -m pmlab.replay --settlements archive/settlements --events events.yaml
python -m pmlab.replay --cache .replaycache/replay.json.gz   # do not re-screen
                                      # unchanged blobs; identical bytes out
python scripts/check_readme.py        # do this file's numbers still match results/?
python -m pytest -q tests             # schema, settlement, fee and screen tests
```

Python 3.10+. `record.py`, `settle.py`, `screen.py` and everything under
`pmlab/` except the plotting step are standard library only; the replay's
SVGs need matplotlib (`--no-plots` skips them), `pmlab.basis` needs PyYAML
to read `events.yaml` (and says so in the output rather than silently
reporting an empty map when it is missing), and the tests need pytest.

## License

MIT
