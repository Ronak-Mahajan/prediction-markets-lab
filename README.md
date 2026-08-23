# prediction-markets-lab

Are quoted event probabilities coherent, and when they disagree, who is
right? A measurement engine for prediction markets, built on the rule
that made the sibling projects work: record first, screen honestly,
and let weeks of data draw the conclusions.

The repo records its own data with no server anywhere: a GitHub Actions
cron snapshots four venues' public APIs every two hours and commits the
result. The history accumulates in `data/` from the day the repo went
live, so every later study has an archive it can replay.

## Venues

| venue | markets per snapshot | source |
|---|---|---|
| Kalshi | ~2,000 events, nested quoted markets | official public API |
| Polymarket | top 1,000 by liquidity | gamma API |
| PredictIt | full catalog (~190) | official API |
| Manifold | ~650 active binaries | official API |

No keys, no scraping; snapshots are trimmed to the fields the screens
need (about 600 KB gzipped each).

## Phase 1 (live): coherence screening

`screen.py` checks the constraints that need no model, only logic:

1. **Complement.** Buying YES and NO at the ask must cost at least $1.
   Reported gross and net of the venue fee, because the first lesson of
   screening real markets is that gross violations are usually the
   spread wearing a costume. First snapshot: 12,720 two-sided Kalshi
   books, zero violations even gross, which is what a single-book venue
   should produce.
2. **Bucket sums.** For a mutually exclusive event, YES asks summing
   below $1 is a candidate underround. Candidate, and the output says
   so loudly: the survivors on the first snapshot (next pope, 51st
   state) are exactly the open-universe events whose listed buckets are
   not exhaustive, the classic trap this check exists to expose rather
   than fall into.
3. **Ladder monotonicity.** Threshold markets on one variable must
   price P(>= s) decreasing in s; a higher strike bidding over a lower
   strike's ask is incoherence beyond the spread. First snapshot: 44
   ladders, zero inversions.

The interesting output is not any single hit; it is the time series of
these counts as snapshots accumulate: how often does anything survive
honest fee accounting, and for how long?

## Phase 2 (planned): cross-venue basis

The same event priced on two venues, matched conservatively (exact
entity and deadline, no fuzzy matching), with the basis measured net of
each side's fees and spread. The deliverable is a distribution of
persistent basis and its decay time, not a screenshot of one gap.

## Phase 3 (planned): does sentiment lead repricing?

Score public news flow (headline feeds, statement diffs for scheduled
events like FOMC) and test, walk-forward and out of sample, whether
sentiment shifts lead prediction-market price moves or lag them. The
recorder's timestamps make the lead-lag question answerable; nothing
gets reported in-sample.

## Phase 4 (planned): model vs market on financial events

Kalshi lists range markets on BTC and equity indexes. A calibrated
options surface implies risk-neutral probabilities for those exact
events ([neural-options-lab](https://github.com/Ronak-Mahajan/neural-options-lab)
calibrates rough Bergomi with jumps to Deribit's BTC surface). The gap
between model probability and market price is risk premium plus
frictions, not free money; the study is its structure and stability.

## Run it

```
python record.py     # one snapshot into data/
python screen.py     # coherence report on the newest snapshot
```

Python 3.10+, standard library only.

## License

MIT
