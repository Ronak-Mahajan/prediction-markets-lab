# Coherence over the archive

Generated 2026-09-11T20:04:02Z by `python -m pmlab.replay` at commit `d259b4e094fc`.

**Archive replayed:** 122 snapshots, 2026-08-23T01:18:06Z to 2026-09-11T19:54:25Z (19.8 days), realised cadence median 3.3 h / max 12.6 h.  
**Archive identity (sha256 of the blob list):** `c2d28bb7f0fd40fce02786ddeff1de56b1aac713d7699e47c611f3ab3d098786`

Every count below is produced twice: **gross**, and **net** of the venue's own fee with the venue's own rounding. The gap between the two columns is the result.

## The one-line answer

Across 122 snapshots and 19.8 days, 308 gross ladder monotonicity inversions were found and 3 survived the fee model; 0 PredictIt and 43 Polymarket complement violations gross, 0 and 43 net; a median 20 bucket-sum candidates per snapshot gross and 8 net, all open-universe events. The Kalshi complement identity held on 1,708,477 of 1,708,477 two-sided books.

Every inversion that survived the fee is in 1 event(s): `KXINXMINY-01JAN2027`. Those are the rows to go and read by hand; everything else in this file is a count.

## Kalshi ladders

| quantity | value |
|---|---|
| ladders per snapshot (median) | 1120.5 |
| ladders per snapshot (min-max, across both recorders) | 848-3,476 |
| rungs per snapshot (median) | 7975.5 |
| adjacent strike pairs tested (total) | 928,215 |
| monotonicity inversions, gross (total) | 308 |
| monotonicity inversions, net of fee (total) | 3 |
| snapshots with any gross inversion | 67 of 122 |
| negative implied mass at mids, gross (total) | 17,367 |
| ... whose magnitude exceeds two legs of fee | 7,788 |

Worst gross inversion: `KXFEDFUNDSYEAR-32JAN01` on 2026-08-26T09:05:55Z, strike 2.25 ask 0.62 against strike 2.5 bid 0.65 -- 3.0c gross, 4.0c of fee on the two legs, -1.0c net.

Recorder v1 stopped at 2,000 events (about 14,000 markets, mostly the two midterm ladder families); recorder v2 sweeps the whole open catalog (about 56,000). Pooling the two counts a different experiment twice, so they are split:

| recorder | snapshots | adjacent pairs | inversions gross | net of fee |
|---|---|---|---|---|
| v1 (2,000-event cap) | 117 | 804,708 | 291 | 0 |
| v2 (full catalog) | 5 | 123,507 | 17 | 3 |

Those 308 inversions are not spread across the catalog: they fall in 27 events.

| event | gross inversions |
|---|---|
| `KXFEDFUNDSYEAR-32JAN01` | 89 |
| `KXFEDFUNDSYEAR-37JAN01` | 52 |
| `KXFEDFUNDSYEAR-34JAN01` | 33 |
| `KXUSCPIYEAR-30FEB01` | 24 |
| `KXFEDFUNDSYEAR-31JAN01` | 19 |
| `KXFEDFUNDSYEAR-33JAN01` | 19 |
| `KXFEDFUNDSYEAR-35JAN01` | 17 |
| `KXFEDFUNDSYEAR-36JAN01` | 10 |
| `KXLFPRATEEOY-33JAN07` | 5 |
| `KXMDT-26DECCARDGROW` | 5 |

The inversion screen is at the touch and is executable by construction: sell the higher strike at its bid, buy the lower at its ask. The negative-mass screen is at mids and is **not** a trade -- it says where the quoted curve is marked impossibly, which is a wider and softer statement. The two must not be read as the same number.

## Complement

| venue | pairs per snapshot (median) | gross (total) | net (total) |
|---|---|---|---|
| Polymarket (quoted outcome pair) | 942 | 43 | 43 |
| PredictIt (YES/NO asks) | 495 | 0 | 0 |
| Kalshi | not screened | - | - |

Kalshi is not screened on purpose: `no_ask == 1 - yes_bid` held on 1,708,477 of 1,708,477 two-sided books across the whole archive (0 deviations), so YES ask plus NO ask is 1 plus the spread by construction and the screen cannot fire. It is asserted as an invariant: a single deviation fails this replay.

Screened on the venue's quoted outcome-price pair, not on two asks: the complementary token's book is not in this archive (a recorder gap). A violation is an incoherent quote, not a demonstrated trade.

All 43 Polymarket violations fall in the 68 snapshots of the string-sorted era (2026-08-23 to 2026-09-01T16:44Z), when the venue served `order=liquidity` sorted as text and the recorder kept the result: thin, often already-expired rows. The 54 snapshots of the clean `liquidityNum` era carry 0. That is a statement about the recorder, not about the venue's quotes.

## Bucket sums

| quantity | value |
|---|---|
| mutually-exclusive events screened per snapshot (median) | 228 |
| candidates per snapshot, gross (median) | 20 |
| candidates per snapshot, net of fee (median) | 8 |

Most persistent candidates (snapshots in which the event was flagged):

| event | snapshots |
|---|---|
| `KXMOLDOVAPRES-28` | 122 |
| `KXNEWPOPE-70` | 122 |
| `KXNEXTSTATE-29` | 122 |
| `KXPRESMATCHUP-28NOV07` | 122 |
| `KXSENATENYD-28` | 122 |
| `KXSTATE51-29` | 122 |
| `KXTRUMPAGCOUNT-29` | 122 |
| `KXVPRESNOMR-28` | 122 |
| `KXNEXTDEPUTYAG-28JAN01` | 121 |
| `KXPRESTAIWAN-28` | 121 |

A bucket-sum candidate is NOT an arbitrage. The venue's mutually_exclusive flag promises at most one bucket settles YES, not that the listed buckets are exhaustive; the survivors on real data are open-universe events (next pope, 51st state, party nominations) whose missing 'someone else' bucket is exactly the mass that makes the asks sum below a dollar. Read the event rules before believing any row of this table.

## Calibration

Settlements read: 33,380 markets from 19 file(s) (kalshi 7,641, manifold 452, polymarket 25,140, predictit 147). Scored forecasts: 4,754 (plus 49 inferred PredictIt outcomes held out of every headline number).

Each market is scored at the **last quote at or before `settled_at - H`**, used only if it is no more than 24 h older than that cut-off. 16,031 market/horizon cells had a quote before the cut-off but only a stale one, and 980 had only a one-sided book; both are reported unscored rather than scored on a price nobody was quoting. The baseline everywhere is a coin flip: Brier 0.25, log score -0.6931.

**Read the `blocks` column before the `n` column.** A block is one venue's settlements on one day, and markets that resolve together do not resolve independently: a thousand forecasts spread over four settlement days is four observations of the world wearing a large `n`. The block bootstrap prices that in and the Wilson interval does not; below 3 blocks no bootstrap interval is reported at all, because resampling two blocks produces an interval about the block count rather than about the data.

### By horizon

| horizon | n | blocks | Brier | 95% block bootstrap | skill vs 50/50 | log score | base rate | median h before settlement |
|---|---|---|---|---|---|---|---|---|
| 1d (1 d) | 3,232 | 52 | 0.1554 | [0.1392, 0.1680] | 0.378 | -0.4632 | 0.381 | 30.6 |
| 1wk (7 d) | 1,522 | 34 | 0.1961 | [0.1594, 0.2207] | 0.216 | -0.5589 | 0.363 | 175.0 |
| 1mo (30 d) | 0 | 0 | - | - | - | - | - | - |
| 2mo (60 d) | 0 | 0 | - | - | - | - | - | - |

- **1mo** is empty because no settled market resolved on or after 2026-09-22T01:18:06Z, which is the earliest settlement this archive can price 1mo ahead (it opens 2026-08-23).
- **2mo** is empty because no settled market resolved on or after 2026-10-22T01:18:06Z, which is the earliest settlement this archive can price 2mo ahead (it opens 2026-08-23).

### By venue and horizon

| venue | horizon | n | blocks | Brier | skill vs 50/50 | log score | mean mid | base rate | median spread (c) |
|---|---|---|---|---|---|---|---|---|---|
| kalshi | 1d | 243 | 14 | 0.0161 | 0.936 | -0.0659 | 0.911 | 0.909 | 1.0 |
| kalshi | 1wk | 159 | 9 | 0.0448 | 0.821 | -0.1749 | 0.534 | 0.478 | 3.0 |
| polymarket | 1d | 2,763 | 19 | 0.1645 | 0.342 | -0.4901 | 0.343 | 0.321 | 5.0 |
| polymarket | 1wk | 1,238 | 12 | 0.2178 | 0.129 | -0.6133 | 0.440 | 0.335 | 92.0 |
| manifold | 1d | 226 | 19 | 0.1938 | 0.225 | -0.5612 | 0.496 | 0.535 | 0.0 |
| manifold | 1wk | 125 | 13 | 0.1734 | 0.306 | -0.5089 | 0.483 | 0.496 | 0.0 |

Everything below is the **1d** horizon, the shortest one this archive can fill.

### What this sample is

3,232 forecasts from 52 venue-days: kalshi 243, manifold 226, polymarket 2,763; Polymarket recorder era numeric 349, string_sorted 2,414.

| settlement day | forecasts |
|---|---|
| polymarket:2026-08-27 | 347 |
| polymarket:2026-08-26 | 335 |
| polymarket:2026-08-25 | 323 |
| polymarket:2026-08-30 | 288 |
| polymarket:2026-08-31 | 234 |
| polymarket:2026-08-24 | 220 |
| polymarket:2026-08-29 | 205 |
| polymarket:2026-08-28 | 151 |

Nothing here is a random sample of a venue's catalog. It is the set of markets that happened to resolve inside a three-week recording window, which skews hard towards short-dated sports and towards whatever the recorder's Polymarket slice contained at the time. Read every score below as a description of that set, not as a venue's calibration.

Join sanity check (not a result): markets that settled YES were quoted at a mean mid of 0.602 and markets that settled NO at 0.270. If the outcome were joined to the wrong side of the book these would be the wrong way round.

### Reliability

Wilson intervals assume the forecasts in a bin are independent. Markets that settle on the same day are not, so a block bootstrap over (venue, settlement day) blocks is reported beside them; where the two disagree, the bootstrap is the honest one.

**all** (52 settlement-day block(s))

| bin | n | mean mid | realised | Wilson 95% | bootstrap 95% |
|---|---|---|---|---|---|
| 0.0-0.1 | 594 | 0.040 | 0.037 | [0.025, 0.055] | [0.017, 0.060] |
| 0.1-0.2 | 269 | 0.147 | 0.108 | [0.076, 0.151] | [0.074, 0.147] |
| 0.2-0.3 | 432 | 0.251 | 0.222 | [0.186, 0.264] | [0.179, 0.277] |
| 0.3-0.4 | 346 | 0.350 | 0.332 | [0.285, 0.384] | [0.282, 0.376] |
| 0.4-0.5 | 573 | 0.462 | 0.372 | [0.333, 0.412] | [0.331, 0.415] |
| 0.5-0.6 | 439 | 0.529 | 0.592 | [0.546, 0.637] | [0.554, 0.633] |
| 0.6-0.7 | 147 | 0.649 | 0.660 | [0.580, 0.732] | [0.600, 0.711] |
| 0.7-0.8 | 92 | 0.740 | 0.739 | [0.641, 0.818] | [0.591, 0.844] |
| 0.8-0.9 | 55 | 0.854 | 0.891 | [0.782, 0.949] | [0.794, 0.975] |
| 0.9-1.0 | 285 | 0.985 | 0.986 | [0.964, 0.995] | [0.966, 0.997] |

**kalshi** (14 settlement-day block(s))

| bin | n | mean mid | realised | Wilson 95% | bootstrap 95% |
|---|---|---|---|---|---|
| 0.0-0.1 | 16 | 0.039 | 0.000 | [0.000, 0.194] | [0.000, 0.000] |
| 0.1-0.2 | 3 | 0.135 | 0.333 | [0.061, 0.792] | [0.000, 1.000] |
| 0.3-0.4 | 1 | 0.385 | 0.000 | [0.000, 0.793] | [0.000, 0.000] |
| 0.6-0.7 | 3 | 0.658 | 1.000 | [0.439, 1.000] | [1.000, 1.000] |
| 0.8-0.9 | 3 | 0.863 | 0.667 | [0.208, 0.939] | [0.000, 1.000] |
| 0.9-1.0 | 217 | 0.992 | 0.991 | [0.967, 0.997] | [0.971, 1.000] |

**manifold** (19 settlement-day block(s))

| bin | n | mean mid | realised | Wilson 95% | bootstrap 95% |
|---|---|---|---|---|---|
| 0.0-0.1 | 19 | 0.045 | 0.000 | [0.000, 0.168] | [0.000, 0.000] |
| 0.1-0.2 | 12 | 0.155 | 0.250 | [0.089, 0.532] | [0.000, 0.538] |
| 0.2-0.3 | 14 | 0.258 | 0.286 | [0.117, 0.546] | [0.077, 0.556] |
| 0.3-0.4 | 23 | 0.361 | 0.348 | [0.188, 0.551] | [0.182, 0.500] |
| 0.4-0.5 | 39 | 0.450 | 0.590 | [0.434, 0.729] | [0.379, 0.757] |
| 0.5-0.6 | 54 | 0.541 | 0.593 | [0.460, 0.713] | [0.471, 0.702] |
| 0.6-0.7 | 24 | 0.635 | 0.667 | [0.467, 0.820] | [0.478, 0.846] |
| 0.7-0.8 | 13 | 0.763 | 0.769 | [0.497, 0.918] | [0.545, 1.000] |
| 0.8-0.9 | 13 | 0.845 | 0.923 | [0.667, 0.986] | [0.765, 1.000] |
| 0.9-1.0 | 15 | 0.965 | 0.867 | [0.621, 0.963] | [0.706, 1.000] |

**polymarket** (19 settlement-day block(s))

| bin | n | mean mid | realised | Wilson 95% | bootstrap 95% |
|---|---|---|---|---|---|
| 0.0-0.1 | 559 | 0.039 | 0.039 | [0.026, 0.059] | [0.017, 0.063] |
| 0.1-0.2 | 254 | 0.147 | 0.098 | [0.068, 0.141] | [0.065, 0.131] |
| 0.2-0.3 | 418 | 0.251 | 0.220 | [0.183, 0.262] | [0.171, 0.277] |
| 0.3-0.4 | 322 | 0.349 | 0.332 | [0.283, 0.385] | [0.278, 0.381] |
| 0.4-0.5 | 534 | 0.463 | 0.356 | [0.316, 0.397] | [0.310, 0.392] |
| 0.5-0.6 | 385 | 0.528 | 0.592 | [0.542, 0.640] | [0.556, 0.635] |
| 0.6-0.7 | 120 | 0.651 | 0.650 | [0.561, 0.729] | [0.591, 0.697] |
| 0.7-0.8 | 79 | 0.736 | 0.734 | [0.628, 0.819] | [0.582, 0.838] |
| 0.8-0.9 | 39 | 0.857 | 0.897 | [0.764, 0.959] | [0.800, 1.000] |
| 0.9-1.0 | 53 | 0.962 | 1.000 | [0.932, 1.000] | [1.000, 1.000] |

### Favourite-longshot bias, on the bid and on the ask

Measured on the traded prices, never on the mid: a longshot buyer pays the ask and a favourite seller receives the bid. `bias` is realised frequency minus mean price in cents, so a negative number means that side was dearer than it was worth.

Manifold quotes a single probability rather than a book, so its bid and ask columns carry the same number; the venue split says how much of each row that is.

**Read the spread column with the bias column.** A two-sided book is not the same thing as a tradeable one: a bin whose median spread is most of a dollar is a bin of nominal quotes sitting on near-empty books, and most of its apparent bias is that fact rather than a market view. The rows are reported rather than filtered out, because picking a spread cut-off is a judgement and applying one silently would be making that judgement for the reader.

**bid**

| bin | n | mean price | realised | bias (c) | median spread (c) | Wilson 95% |
|---|---|---|---|---|---|---|
| 0.0-0.1 | 1,310 | 0.029 | 0.168 | 13.9 | 21.0 | [0.149, 0.189] |
| 0.1-0.2 | 262 | 0.143 | 0.221 | 7.8 | 3.0 | [0.175, 0.275] |
| 0.2-0.3 | 331 | 0.246 | 0.269 | 2.3 | 3.0 | [0.224, 0.319] |
| 0.3-0.4 | 268 | 0.347 | 0.422 | 7.5 | 4.0 | [0.364, 0.481] |
| 0.4-0.5 | 296 | 0.449 | 0.497 | 4.8 | 3.0 | [0.440, 0.553] |
| 0.5-0.6 | 228 | 0.541 | 0.605 | 6.4 | 1.0 | [0.541, 0.666] |
| 0.6-0.7 | 144 | 0.646 | 0.653 | 0.7 | 3.0 | [0.572, 0.726] |
| 0.7-0.8 | 65 | 0.741 | 0.800 | 5.9 | 4.0 | [0.687, 0.879] |
| 0.8-0.9 | 56 | 0.849 | 0.893 | 4.4 | 2.0 | [0.785, 0.950] |
| 0.9-1.0 | 272 | 0.982 | 0.989 | 0.7 | 1.0 | [0.968, 0.996] |

**ask**

| bin | n | mean price | realised | bias (c) | median spread (c) | Wilson 95% |
|---|---|---|---|---|---|---|
| 0.0-0.1 | 499 | 0.041 | 0.026 | -1.5 | 1.6 | [0.015, 0.044] |
| 0.1-0.2 | 271 | 0.143 | 0.107 | -3.6 | 3.0 | [0.076, 0.149] |
| 0.2-0.3 | 289 | 0.247 | 0.187 | -6.0 | 2.0 | [0.146, 0.236] |
| 0.3-0.4 | 284 | 0.346 | 0.320 | -2.6 | 3.0 | [0.269, 0.377] |
| 0.4-0.5 | 350 | 0.447 | 0.397 | -5.0 | 5.0 | [0.347, 0.449] |
| 0.5-0.6 | 393 | 0.536 | 0.463 | -7.3 | 4.0 | [0.414, 0.513] |
| 0.6-0.7 | 180 | 0.639 | 0.544 | -9.5 | 5.0 | [0.472, 0.616] |
| 0.7-0.8 | 146 | 0.742 | 0.610 | -13.3 | 7.5 | [0.529, 0.685] |
| 0.8-0.9 | 132 | 0.848 | 0.583 | -26.5 | 56.5 | [0.498, 0.664] |
| 0.9-1.0 | 688 | 0.972 | 0.666 | -30.6 | 86.0 | [0.630, 0.700] |

### By category

| slice | n | blocks | Brier | skill vs 50/50 | log score | base rate |
|---|---|---|---|---|---|---|
| Elections | 222 | 11 | 0.0157 | 0.937 | -0.0629 | 0.941 |
| Entertainment | 4 | 2 | 0.0653 | 0.739 | -0.2536 | 1.000 |
| Politics | 5 | 3 | 0.0228 | 0.909 | -0.0968 | 0.600 |
| Sports | 12 | 4 | 0.0039 | 0.984 | -0.0463 | 0.417 |
| unknown | 2,989 | 38 | 0.1667 | 0.333 | -0.4955 | 0.338 |

Category is recorded on Kalshi only; the recorder captures no category for Polymarket or Manifold, so every row from those venues is `unknown`. That is a recorder gap, not a market fact.

### By liquidity bucket

| slice | n | blocks | Brier | skill vs 50/50 | log score | base rate |
|---|---|---|---|---|---|---|
| 100-1k | 1,110 | 19 | 0.1397 | 0.441 | -0.4244 | 0.321 |
| 10k-100k | 191 | 23 | 0.1282 | 0.487 | -0.3980 | 0.372 |
| 1k-10k | 703 | 23 | 0.1259 | 0.496 | -0.3799 | 0.486 |
| <100 | 786 | 14 | 0.1938 | 0.225 | -0.5649 | 0.333 |
| >=100k | 216 | 14 | 0.1759 | 0.296 | -0.5187 | 0.361 |
| unknown | 226 | 19 | 0.1938 | 0.225 | -0.5612 | 0.535 |

Each venue's own liquidity measure, so these bands compare markets within a venue and not across venues: kalshi = open_interest (contracts); manifold = totalLiquidity; polymarket = liquidityNum (USD); predictit = none recorded

### By Polymarket recorder era

| slice | n | blocks | Brier | skill vs 50/50 | log score | base rate |
|---|---|---|---|---|---|---|
| numeric | 349 | 10 | 0.1672 | 0.331 | -0.4946 | 0.309 |
| string_sorted | 2,414 | 11 | 0.1641 | 0.344 | -0.4895 | 0.323 |

The string-sorted era is the nine days the venue served `order=liquidity` as text and the recorder kept the result.

### Inferred outcomes (excluded from every number above)

PredictIt outcomes are inferred from the last trade of a contract that left the public feed, not observed. These scores are reported so the inference can be judged, and are excluded from every headline number.

| horizon | n | Brier | skill vs 50/50 |
|---|---|---|---|
| 1d | 16 | 0.1419 | 0.432 |
| 1wk | 33 | 0.1427 | 0.429 |

Settlement records read but not scoreable:

| venue | reason | records |
|---|---|---|
| kalshi | result=scalar | 3 |
| manifold | resolution=CANCEL | 19 |
| manifold | resolution=MKT | 12 |
| polymarket | outcome price not 0 or 1 | 106 |

## Cross-venue basis

Curation rule: **identical entity and identical deadline on both venues, read off both rules pages by a person; no fuzzy matching**.

`events.yaml`: 5 pair(s), 0 verified, 5 awaiting a hand check.

No verified cross-venue pair is in events.yaml, so there is no basis to measure. The file ships as a skeleton of examples marked `verified: false`; pairing is a hand check of both venues' rules pages (identical entity, identical deadline) and unverified pairs are counted here and never priced.

Awaiting verification: `fed-2026-09-hike-25bp`, `fed-2026-09-hike-any`, `govt-shutdown-2026-10-01`, `nobel-peace-2026-musk`, `recession-2027-nber`.

## Fee models in force

Constants read 2026-09-11.

| venue | model |
|---|---|
| kalshi | taker fee = ceil to the cent of 0.07 * contracts * P * (1-P), per order; minimum one cent per order with any risk |
| polymarket | no taker fee on the CLOB; per-market overrides supported |
| predictit | 10% of profit on the winning leg, plus 5% on withdrawal |

- **kalshi:** the reduced-multiplier series table is EMPTY (the fee schedule PDF has not been read here), so every series is charged the general 0.07 multiplier
- **polymarket:** with a zero fee the net numbers equal the gross ones by construction; they are reported separately anyway so the day a fee appears the table changes on its own
- **predictit:** the profit fee is charged per winning position, so a complement pair is quoted at its worst case

## Figures

![Ladders and rungs parsed per snapshot](ladders.svg)

![Ladder monotonicity inversions per snapshot, gross and net](ladder_inversions.svg)

![Adjacent strike pairs with negative implied mass](negative_mass.svg)

![Complement violations per snapshot by venue](complement.svg)

![Bucket-sum candidates per snapshot, gross and net](buckets.svg)

![Reliability of the mid, by venue, with Wilson intervals](reliability.svg)

![Favourite-longshot bias measured on the bid and on the ask](favourite_longshot.svg)

## Reproduce

```
python -m pmlab.replay --roots data
```

`timeseries.csv` carries one row per snapshot and every column behind these tables; `summary.json` carries the same numbers plus the worst case for each screen with its ticker. Neither file is edited by hand.
