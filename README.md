# prediction-markets-lab

Are quoted event probabilities coherent, and when they disagree, who is
right? A measurement engine for prediction markets, built on the rule
that made the sibling projects work: record first, screen honestly,
and let weeks of data draw the conclusions.

The repo records its own data with no server anywhere: a GitHub Actions
cron snapshots four venues' public APIs and commits the result. The cron
is scheduled every two hours; across the first 116 snapshot intervals
the realised cadence is a median 3.3 h with a maximum gap of 12.6 h
(2026-08-27 and 08-28 have two snapshots each), because hosted schedulers
delay runs under load. Every run succeeded, so the gaps are scheduler
delay, not failures. The history accumulates from the day the repo went
live, so every later study has an archive it can replay.

## Venues

| venue | recorded per snapshot (recorder v2) | source |
|---|---|---|
| Kalshi | every open non-Sports market plus the 3,000 highest-open-interest Sports markets (about 48,000 markets across about 6,000 events; 123,155 open markets swept on 2026-09-11, 77,996 of them Sports), with event metadata | official public API v2 |
| Polymarket | top 1,000 by `liquidityNum`, sorted client-side, rows already past their `endDate` dropped | gamma API |
| PredictIt | full catalog (about 190 markets, about 590 contracts) | official API |
| Manifold | 1,000 most liquid open binaries (`search-markets?sort=liquidity`) | official API |

No keys, no scraping; snapshots are trimmed to the fields the studies
need. Recorder v1 (2026-08-23 to the merge of this branch) recorded the
first 2,000 Kalshi events (about 14,000 markets, dominated by the two
midterm ladder families), Polymarket as served, and Manifold's 1,000
newest markets; those blobs are kept unchanged and load through the same
loader (see "Provenance and corrections").

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
went stale unnoticed. Every figure below therefore carries the archive it
was measured on.

**Archive replayed:** 119 <!-- results:archive.snapshots --> snapshots,
2026-08-23 to 2026-09-11, 19.6 <!-- results:archive.days_spanned -->
days, realised cadence median
3.4 <!-- results:archive.median_gap_hours --> h.

**Ladders.** A median of
1,120 <!-- results:ladders.median_per_snapshot --> threshold ladders per
snapshot (7,975 <!-- results:ladders.rungs_median_per_snapshot --> rungs)
give 854,961 <!-- results:ladders.adjacent_pairs_total --> adjacent
strike pairs tested across the archive.
306 <!-- results:ladders.inversions_gross_total --> of them are gross
monotonicity inversions — a higher strike bid over a lower strike's ask —
spread over 64 <!-- results:ladders.snapshots_with_gross_inversion --> of
the 119 <!-- results:archive.snapshots --> snapshots.
**6 <!-- results:ladders.inversions_net_total --> survive the venue's
taker fee.** The widest gross edge in the whole archive was 3.0c, on a
Fed-funds ladder, against 4.0c of fee on the two legs. The fee model is
the published formula *with the published rounding* — ceil to the cent
per order, so the smallest fee on any risky contract is a full cent and a
two-legged trade starts two cents behind. The old screen charged the
unrounded `0.07·p·(1-p)`, which at a one-cent contract is fourteen times
too little, and that is the entire difference between "a one-cent edge
survives" and "it does not".

At mids rather than at the touch, the same ladders imply negative
probability mass between adjacent strikes
14,417 <!-- results:ladders.negative_mass_gross_total --> times. That is
a statement about where quotes are marked, not a trade, and the two
numbers are kept apart on purpose.

**Complement.** Kalshi is not screened, because it cannot fire there:
`no_ask == 1 - yes_bid` held on
1,572,862 <!-- results:kalshi_identity.books_checked_total --> of
1,572,862 <!-- results:kalshi_identity.books_checked_total --> two-sided
books, 0 <!-- results:kalshi_identity.deviations_total --> deviations, so
YES ask + NO ask is 1 + spread by construction. The replay asserts the
identity and fails if it ever breaks. Where the screen can fire:
58,197 <!-- results:predictit_complement.pairs_total --> PredictIt
YES/NO ask pairs give
0 <!-- results:predictit_complement.gross_total --> violations gross, and
111,386 <!-- results:polymarket_complement.pairs_total --> Polymarket
quoted outcome pairs give
43 <!-- results:polymarket_complement.gross_total --> — all
43 <!-- results:polymarket_complement.gross_string_sorted_era --> of them
inside the string-sorted era, and
0 <!-- results:polymarket_complement.gross_numeric_era --> in the
51 <!-- results:polymarket_complement.snapshots_numeric_era --> clean
snapshots. The incoherent quotes are in the rows the recorder's broken
sort surfaced, which makes that a finding about this repo rather than
about Polymarket.

**Bucket sums.** A median of
228 <!-- results:buckets.screened_median_per_snapshot --> mutually
exclusive events per snapshot are fully quoted;
20 <!-- results:buckets.candidates_gross_median --> of them sum below a
dollar gross and 8 <!-- results:buckets.candidates_net_median --> net of
fees. The same tickers recur in all
119 <!-- results:archive.snapshots --> snapshots — next pope, 51st state,
party nominations, Moldovan president — which is the open-universe trap
this screen exists to name rather than fall into: the missing "someone
else" bucket is the missing mass.

**The one-line answer, dated 2026-09-11.** Over
119 <!-- results:archive.snapshots --> snapshots and
19.6 <!-- results:archive.days_spanned --> days of four venues'
top-of-book quotes, honest fee accounting erases every coherence
violation the screens can find: 291 gross ladder inversions go to zero,
the only complement violations are in known-bad recorder output, and the
bucket-sum survivors are exactly the events whose buckets are not
exhaustive. That is a negative result, and it is published at the size a
positive one would get.

### Still to come in Phase 2

The same event priced on two venues, matched conservatively (a
hand-curated event map; exact title matching yields zero pairs), with the
basis measured net of each side's fees and spread. The deliverable is a
distribution of persistent basis and its decay time, not a screenshot of
one gap.

## Phase 3 (planned): does sentiment lead repricing?

Score public news flow (headline feeds, statement diffs for scheduled
events like FOMC) and test, walk-forward and out of sample, whether
sentiment shifts lead prediction-market price moves or lag them. The
recorder's timestamps make the lead-lag question answerable; nothing
gets reported in-sample.

## Phase 4 (planned): model vs market on financial events

Kalshi lists range markets on equity indexes (KXINXY, KXINXDIRY and the
daily KXNASDAQ100U family are in the archive; no KXBTC range series was
captured by recorder v1). A calibrated options surface implies
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
python scripts/check_readme.py        # do this file's numbers still match results/?
python -m pytest -q tests             # schema, settlement, fee and screen tests
```

Python 3.10+. `record.py`, `settle.py`, `screen.py` and everything under
`pmlab/` except the plotting step are standard library only; the replay's
SVGs need matplotlib (`--no-plots` skips them) and the tests need pytest.

## License

MIT
