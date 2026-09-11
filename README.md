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
   inversions" figure previously quoted here was measured on 2026-08-23
   with a title regex that matched about 3% of markets; it is a coverage
   artifact of that regex, and the count under the same regex was 27 on
   2026-09-10. Recorder v2 records the venue's structured strike fields
   (`strike_type`, `floor_strike`, `cap_strike`), and the ladder count
   will be regenerated from those by the Phase 2 replay and dated.

The interesting output is not any single hit; it is the time series of
these counts as snapshots accumulate: how often does anything survive
honest fee accounting, and for how long? That series is produced by the
replay CLI in Phase 2 (in progress on this branch); `screen.py` today
reads one snapshot.

## Phase 2 (in progress on this branch): archive replay and cross-venue basis

Coherence over the whole archive as a time series, every count gross and
net of each venue's real fee, regenerated by CI from the committed
archive with the manifest hash of the data it ran on. Then the same
event priced on two venues, matched conservatively (a hand-curated event
map; exact title matching yields zero pairs), with the basis measured
net of each side's fees and spread. The deliverable is a distribution of
persistent basis and its decay time, not a screenshot of one gap.

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
- Every number in this README is dated; numbers that a script produces
  will be regenerated by CI and checked against the results it commits.

## Run it

```
python record.py                      # one snapshot into data/
python record.py --out archive/data   # the data-branch layout used by CI
python settle.py --archive archive --snapshots data
python screen.py                      # coherence report on the newest snapshot
python -m pytest -q tests             # schema, settlement and manifest tests
```

Python 3.10+, standard library only (pytest for the tests).

## License

MIT
