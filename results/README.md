# Coherence over the archive

Generated 2026-09-16T07:11:27Z by `python -m pmlab.replay` at commit `511391f6f945`.

**Archive replayed:** 150 snapshots, 2026-08-23T01:18:06Z to 2026-09-16T00:27:34Z (24.0 days), realised cadence median 3.4 h / max 12.6 h.  
**Archive identity (sha256 of the blob list):** `4f998dda7602e8f02c392ca571bc2f53f1887b376e761ca4ea507139f8cd0ef4`

Every count below is produced twice: **gross**, and **net** of the venue's own fee with the venue's own rounding. The gap between the two columns is the result.

## The one-line answer

Across 150 snapshots and 24.0 days, 400 gross ladder monotonicity inversions were found and 7 survived the fee model; 0 PredictIt and 43 Polymarket complement violations gross, 0 and 43 net; a median 21 bucket-sum candidates per snapshot gross and 9 net, all open-universe events. The Kalshi complement identity held on 2,736,645 of 2,736,645 two-sided books.

Every inversion that survived the fee is in 2 event(s): `KXARTISTSTREAMSY-ODDMOB26DEC31`, `KXINXMINY-01JAN2027`. Those are the rows to go and read by hand; everything else in this file is a count.

## Kalshi ladders

| quantity | value |
|---|---|
| ladders per snapshot (median) | 1145.5 |
| ladders per snapshot (min-max, across both recorders) | 848-3,527 |
| rungs per snapshot (median) | 8,207 |
| adjacent strike pairs tested (total) | 1,489,858 |
| monotonicity inversions, gross (total) | 400 |
| monotonicity inversions, net of fee (total) | 7 |
| snapshots with any gross inversion | 89 of 150 |
| negative implied mass at mids, gross (total) | 42,278 |
| ... whose magnitude exceeds two legs of fee | 17,777 |

Worst gross inversion: `KXARTISTSTREAMSY-ODDMOB26DEC31` on 2026-09-14T19:27:24Z, strike 1.25e+08 ask 0.49 against strike 1.3e+08 bid 0.54 -- 5.0c gross, 4.0c of fee on the two legs, 1.0c net.

Recorder v1 stopped at 2,000 events (about 14,000 markets, mostly the two midterm ladder families); recorder v2 sweeps the whole open catalog (about 56,000). Pooling the two counts a different experiment twice, so they are split:

| recorder | snapshots | adjacent pairs | inversions gross | net of fee |
|---|---|---|---|---|
| v1 (2,000-event cap) | 125 | 861,844 | 293 | 0 |
| v2 (full catalog) | 25 | 628,014 | 107 | 7 |

Those 400 inversions are not spread across the catalog: they fall in 68 events.

| event | gross inversions |
|---|---|
| `KXFEDFUNDSYEAR-32JAN01` | 89 |
| `KXFEDFUNDSYEAR-37JAN01` | 52 |
| `KXFEDFUNDSYEAR-34JAN01` | 33 |
| `KXUSCPIYEAR-30FEB01` | 24 |
| `KXFEDFUNDSYEAR-31JAN01` | 19 |
| `KXFEDFUNDSYEAR-33JAN01` | 19 |
| `KXFEDFUNDSYEAR-35JAN01` | 17 |
| `KXFEDFUNDSYEAR-28JAN01` | 13 |
| `KXMDT-26DECCARDGROW` | 12 |
| `KXFEDFUNDSYEAR-36JAN01` | 10 |

The inversion screen is at the touch and is executable by construction: sell the higher strike at its bid, buy the lower at its ask. The negative-mass screen is at mids and is **not** a trade -- it says where the quoted curve is marked impossibly, which is a wider and softer statement. The two must not be read as the same number.

## Complement

| venue | pairs per snapshot (median) | gross (total) | net (total) |
|---|---|---|---|
| Polymarket (quoted outcome pair) | 934.5 | 43 | 43 |
| PredictIt (YES/NO asks) | 497.5 | 0 | 0 |
| Kalshi | not screened | - | - |

Kalshi is not screened on purpose: `no_ask == 1 - yes_bid` held on 2,736,645 of 2,736,645 two-sided books across the whole archive (0 deviations), so YES ask plus NO ask is 1 plus the spread by construction and the screen cannot fire. It is asserted as an invariant: a single deviation fails this replay.

Screened on the venue's quoted outcome-price pair, not on two asks: the complementary token's book is not in this archive (a recorder gap). A violation is an incoherent quote, not a demonstrated trade.

All 43 Polymarket violations fall in the 68 snapshots of the string-sorted era (2026-08-23 to 2026-09-01T16:44Z), when the venue served `order=liquidity` sorted as text and the recorder kept the result: thin, often already-expired rows. The 82 snapshots of the clean `liquidityNum` era carry 0. That is a statement about the recorder, not about the venue's quotes.

## Bucket sums

| quantity | value |
|---|---|
| mutually-exclusive events screened per snapshot (median) | 228 |
| candidates per snapshot, gross (median) | 21 |
| candidates per snapshot, net of fee (median) | 9 |

Most persistent candidates (snapshots in which the event was flagged):

| event | snapshots |
|---|---|
| `KXMOLDOVAPRES-28` | 150 |
| `KXNEWPOPE-70` | 150 |
| `KXNEXTSTATE-29` | 150 |
| `KXPRESMATCHUP-28NOV07` | 150 |
| `KXSENATENYD-28` | 150 |
| `KXSTATE51-29` | 150 |
| `KXTRUMPAGCOUNT-29` | 150 |
| `KXVPRESNOMR-28` | 150 |
| `KXNEXTDEPUTYAG-28JAN01` | 149 |
| `KXPRESTAIWAN-28` | 149 |

A bucket-sum candidate is NOT an arbitrage. The venue's mutually_exclusive flag promises at most one bucket settles YES, not that the listed buckets are exhaustive; the survivors on real data are open-universe events (next pope, 51st state, party nominations) whose missing 'someone else' bucket is exactly the mass that makes the asks sum below a dollar. Read the event rules before believing any row of this table.

## Calibration

Settlements read: 88,688 markets from 31 file(s) (kalshi 59,061, manifold 513, polymarket 28,967, predictit 147). Scored forecasts: 10,669 (plus 49 inferred PredictIt outcomes held out of every headline number).

Each market is scored at the **last quote at or before `settled_at - H`**, used only if it is no more than 24 h older than that cut-off. 18,589 market/horizon cells had a quote before the cut-off but only a stale one, and 4,012 had only a one-sided book; both are reported unscored rather than scored on a price nobody was quoting. The baseline everywhere is a coin flip: Brier 0.25, log score -0.6931.

**Read the `blocks` column before the `n` column.** A block is one venue's settlements on one day, and markets that resolve together do not resolve independently: a thousand forecasts spread over four settlement days is four observations of the world wearing a large `n`. The block bootstrap prices that in and the Wilson interval does not; below 3 blocks no bootstrap interval is reported at all, because resampling two blocks produces an interval about the block count rather than about the data.

### By horizon

| horizon | n | blocks | Brier | 95% block bootstrap | skill vs 50/50 | log score | base rate | median h before settlement |
|---|---|---|---|---|---|---|---|---|
| 1d (1 d) | 9,091 | 64 | 0.1123 | [0.0886, 0.1596] | 0.551 | -0.3576 | 0.492 | 27.0 |
| 1wk (7 d) | 1,578 | 43 | 0.1953 | [0.1653, 0.2187] | 0.219 | -0.5568 | 0.371 | 174.6 |
| 1mo (30 d) | 0 | 0 | - | - | - | - | - | - |
| 2mo (60 d) | 0 | 0 | - | - | - | - | - | - |

- **1mo** is empty because no settled market resolved on or after 2026-09-22T01:18:06Z, which is the earliest settlement this archive can price 1mo ahead (it opens 2026-08-23).
- **2mo** is empty because no settled market resolved on or after 2026-10-22T01:18:06Z, which is the earliest settlement this archive can price 2mo ahead (it opens 2026-08-23).

### By venue and horizon

| venue | horizon | n | blocks | Brier | skill vs 50/50 | log score | mean mid | base rate | median spread (c) |
|---|---|---|---|---|---|---|---|---|---|
| kalshi | 1d | 5,778 | 18 | 0.0789 | 0.684 | -0.2732 | 0.564 | 0.574 | 10.0 |
| kalshi | 1wk | 166 | 10 | 0.0520 | 0.792 | -0.1932 | 0.537 | 0.500 | 3.0 |
| polymarket | 1d | 3,042 | 23 | 0.1685 | 0.326 | -0.5000 | 0.348 | 0.331 | 4.0 |
| polymarket | 1wk | 1,252 | 16 | 0.2159 | 0.136 | -0.6084 | 0.439 | 0.335 | 92.0 |
| manifold | 1d | 271 | 23 | 0.1928 | 0.229 | -0.5580 | 0.499 | 0.539 | 0.0 |
| manifold | 1wk | 160 | 17 | 0.1822 | 0.271 | -0.5306 | 0.493 | 0.512 | 0.0 |

Everything below is the **1d** horizon, the shortest one this archive can fill.

### What this sample is

9,091 forecasts from 64 venue-days: kalshi 5,778, manifold 271, polymarket 3,042; Polymarket recorder era numeric 628, string_sorted 2,414.

| settlement day | forecasts |
|---|---|
| kalshi:2026-09-14 | 3,868 |
| kalshi:2026-09-13 | 841 |
| kalshi:2026-09-12 | 496 |
| polymarket:2026-08-27 | 347 |
| polymarket:2026-08-26 | 335 |
| kalshi:2026-09-15 | 330 |
| polymarket:2026-08-25 | 323 |
| polymarket:2026-08-30 | 288 |

Nothing here is a random sample of a venue's catalog. It is the set of markets that happened to resolve inside a three-week recording window, which skews hard towards short-dated sports and towards whatever the recorder's Polymarket slice contained at the time. Read every score below as a description of that set, not as a venue's calibration.

Join sanity check (not a result): markets that settled YES were quoted at a mean mid of 0.735 and markets that settled NO at 0.252. If the outcome were joined to the wrong side of the book these would be the wrong way round.

### Reliability

Wilson intervals assume the forecasts in a bin are independent. Markets that settle on the same day are not, so a block bootstrap over (venue, settlement day) blocks is reported beside them; where the two disagree, the bootstrap is the honest one.

**all** (64 settlement-day block(s))

| bin | n | mean mid | realised | Wilson 95% | bootstrap 95% |
|---|---|---|---|---|---|
| 0.0-0.1 | 1,327 | 0.041 | 0.024 | [0.017, 0.034] | [0.013, 0.042] |
| 0.1-0.2 | 801 | 0.153 | 0.079 | [0.062, 0.099] | [0.049, 0.140] |
| 0.2-0.3 | 1,067 | 0.247 | 0.142 | [0.123, 0.165] | [0.080, 0.263] |
| 0.3-0.4 | 697 | 0.349 | 0.280 | [0.248, 0.314] | [0.229, 0.353] |
| 0.4-0.5 | 1,101 | 0.461 | 0.394 | [0.366, 0.423] | [0.322, 0.460] |
| 0.5-0.6 | 810 | 0.535 | 0.581 | [0.547, 0.615] | [0.536, 0.619] |
| 0.6-0.7 | 488 | 0.648 | 0.797 | [0.759, 0.830] | [0.593, 0.876] |
| 0.7-0.8 | 540 | 0.754 | 0.919 | [0.892, 0.939] | [0.671, 0.963] |
| 0.8-0.9 | 625 | 0.833 | 0.979 | [0.965, 0.988] | [0.893, 0.987] |
| 0.9-1.0 | 1,635 | 0.969 | 0.996 | [0.992, 0.998] | [0.982, 0.999] |

**kalshi** (18 settlement-day block(s))

| bin | n | mean mid | realised | Wilson 95% | bootstrap 95% |
|---|---|---|---|---|---|
| 0.0-0.1 | 726 | 0.042 | 0.014 | [0.007, 0.025] | [0.004, 0.027] |
| 0.1-0.2 | 511 | 0.156 | 0.057 | [0.040, 0.080] | [0.030, 0.165] |
| 0.2-0.3 | 582 | 0.242 | 0.070 | [0.052, 0.094] | [0.034, 0.258] |
| 0.3-0.4 | 321 | 0.348 | 0.218 | [0.176, 0.266] | [0.083, 0.335] |
| 0.4-0.5 | 442 | 0.460 | 0.394 | [0.349, 0.440] | [0.161, 0.523] |
| 0.5-0.6 | 302 | 0.543 | 0.576 | [0.520, 0.631] | [0.402, 0.648] |
| 0.6-0.7 | 328 | 0.649 | 0.866 | [0.825, 0.899] | [0.444, 0.925] |
| 0.7-0.8 | 440 | 0.756 | 0.959 | [0.936, 0.974] | [0.625, 0.981] |
| 0.8-0.9 | 568 | 0.831 | 0.986 | [0.972, 0.993] | [0.920, 1.000] |
| 0.9-1.0 | 1,558 | 0.970 | 0.998 | [0.994, 0.999] | [0.990, 1.000] |

**manifold** (23 settlement-day block(s))

| bin | n | mean mid | realised | Wilson 95% | bootstrap 95% |
|---|---|---|---|---|---|
| 0.0-0.1 | 20 | 0.045 | 0.000 | [0.000, 0.161] | [0.000, 0.000] |
| 0.1-0.2 | 13 | 0.153 | 0.231 | [0.082, 0.503] | [0.000, 0.500] |
| 0.2-0.3 | 17 | 0.257 | 0.235 | [0.096, 0.473] | [0.059, 0.467] |
| 0.3-0.4 | 29 | 0.363 | 0.310 | [0.173, 0.492] | [0.160, 0.435] |
| 0.4-0.5 | 46 | 0.451 | 0.630 | [0.486, 0.755] | [0.447, 0.792] |
| 0.5-0.6 | 74 | 0.539 | 0.581 | [0.467, 0.687] | [0.463, 0.667] |
| 0.6-0.7 | 26 | 0.634 | 0.692 | [0.500, 0.835] | [0.480, 0.852] |
| 0.7-0.8 | 13 | 0.763 | 0.769 | [0.497, 0.918] | [0.533, 1.000] |
| 0.8-0.9 | 13 | 0.845 | 0.923 | [0.667, 0.986] | [0.769, 1.000] |
| 0.9-1.0 | 20 | 0.969 | 0.900 | [0.699, 0.972] | [0.765, 1.000] |

**polymarket** (23 settlement-day block(s))

| bin | n | mean mid | realised | Wilson 95% | bootstrap 95% |
|---|---|---|---|---|---|
| 0.0-0.1 | 581 | 0.040 | 0.038 | [0.025, 0.057] | [0.018, 0.059] |
| 0.1-0.2 | 277 | 0.147 | 0.112 | [0.080, 0.154] | [0.078, 0.148] |
| 0.2-0.3 | 468 | 0.252 | 0.229 | [0.193, 0.269] | [0.180, 0.288] |
| 0.3-0.4 | 347 | 0.349 | 0.334 | [0.287, 0.386] | [0.283, 0.382] |
| 0.4-0.5 | 613 | 0.462 | 0.377 | [0.339, 0.416] | [0.334, 0.426] |
| 0.5-0.6 | 434 | 0.529 | 0.585 | [0.538, 0.631] | [0.548, 0.621] |
| 0.6-0.7 | 134 | 0.650 | 0.649 | [0.565, 0.725] | [0.587, 0.699] |
| 0.7-0.8 | 87 | 0.739 | 0.736 | [0.634, 0.817] | [0.590, 0.843] |
| 0.8-0.9 | 44 | 0.855 | 0.909 | [0.788, 0.964] | [0.821, 1.000] |
| 0.9-1.0 | 57 | 0.961 | 0.982 | [0.907, 0.997] | [0.934, 1.000] |

### Favourite-longshot bias, on the bid and on the ask

Measured on the traded prices, never on the mid: a longshot buyer pays the ask and a favourite seller receives the bid. `bias` is realised frequency minus mean price in cents, so a negative number means that side was dearer than it was worth.

Manifold quotes a single probability rather than a book, so its bid and ask columns carry the same number; the venue split says how much of each row that is.

**Read the spread column with the bias column.** A two-sided book is not the same thing as a tradeable one: a bin whose median spread is most of a dollar is a bin of nominal quotes sitting on near-empty books, and most of its apparent bias is that fact rather than a market view. The rows are reported rather than filtered out, because picking a spread cut-off is a judgement and applying one silently would be making that judgement for the reader.

**bid**

| bin | n | mean price | realised | bias (c) | median spread (c) | Wilson 95% |
|---|---|---|---|---|---|---|
| 0.0-0.1 | 3,008 | 0.030 | 0.092 | 6.1 | 24.0 | [0.082, 0.103] |
| 0.1-0.2 | 674 | 0.140 | 0.202 | 6.2 | 6.0 | [0.173, 0.234] |
| 0.2-0.3 | 644 | 0.245 | 0.321 | 7.6 | 3.5 | [0.287, 0.358] |
| 0.3-0.4 | 622 | 0.341 | 0.523 | 18.1 | 7.0 | [0.483, 0.562] |
| 0.4-0.5 | 737 | 0.448 | 0.612 | 16.4 | 3.0 | [0.576, 0.646] |
| 0.5-0.6 | 731 | 0.541 | 0.729 | 18.8 | 6.0 | [0.696, 0.760] |
| 0.6-0.7 | 653 | 0.635 | 0.871 | 23.7 | 34.0 | [0.843, 0.895] |
| 0.7-0.8 | 272 | 0.737 | 0.893 | 15.6 | 15.5 | [0.851, 0.925] |
| 0.8-0.9 | 412 | 0.822 | 0.971 | 14.9 | 20.0 | [0.950, 0.983] |
| 0.9-1.0 | 1,338 | 0.971 | 0.996 | 2.5 | 1.0 | [0.991, 0.998] |

**ask**

| bin | n | mean price | realised | bias (c) | median spread (c) | Wilson 95% |
|---|---|---|---|---|---|---|
| 0.0-0.1 | 1,103 | 0.043 | 0.016 | -2.7 | 1.0 | [0.010, 0.026] |
| 0.1-0.2 | 589 | 0.140 | 0.095 | -4.5 | 3.0 | [0.074, 0.121] |
| 0.2-0.3 | 573 | 0.246 | 0.164 | -8.2 | 3.0 | [0.136, 0.197] |
| 0.3-0.4 | 747 | 0.346 | 0.199 | -14.7 | 12.0 | [0.172, 0.230] |
| 0.4-0.5 | 951 | 0.446 | 0.281 | -16.6 | 9.0 | [0.253, 0.310] |
| 0.5-0.6 | 798 | 0.538 | 0.414 | -12.5 | 4.5 | [0.380, 0.448] |
| 0.6-0.7 | 399 | 0.640 | 0.539 | -10.1 | 9.0 | [0.490, 0.587] |
| 0.7-0.8 | 357 | 0.744 | 0.653 | -9.2 | 20.0 | [0.602, 0.700] |
| 0.8-0.9 | 365 | 0.847 | 0.764 | -8.3 | 37.0 | [0.718, 0.805] |
| 0.9-1.0 | 3,209 | 0.984 | 0.883 | -10.2 | 20.0 | [0.871, 0.893] |

### By category

| slice | n | blocks | Brier | skill vs 50/50 | log score | base rate |
|---|---|---|---|---|---|---|
| Climate and Weather | 628 | 2 | 0.0927 | 0.629 | -0.2972 | 0.218 |
| Commodities | 204 | 2 | 0.0983 | 0.607 | -0.3136 | 0.436 |
| Companies | 1 | 1 | 0.0009 | 0.996 | -0.0305 | 1.000 |
| Crypto | 415 | 2 | 0.0725 | 0.710 | -0.2395 | 0.798 |
| Economics | 151 | 3 | 0.0482 | 0.807 | -0.1595 | 0.728 |
| Elections | 224 | 12 | 0.0157 | 0.937 | -0.0637 | 0.938 |
| Entertainment | 598 | 6 | 0.0930 | 0.628 | -0.2951 | 0.445 |
| Financials | 2,709 | 3 | 0.0589 | 0.764 | -0.2405 | 0.678 |
| Mentions | 208 | 3 | 0.1849 | 0.260 | -0.5360 | 0.341 |
| Politics | 44 | 6 | 0.0422 | 0.831 | -0.1536 | 0.523 |
| Science and Technology | 61 | 2 | 0.0375 | 0.850 | -0.1455 | 0.607 |
| Sports | 535 | 8 | 0.1476 | 0.410 | -0.4391 | 0.387 |
| unknown | 3,313 | 46 | 0.1705 | 0.318 | -0.5047 | 0.348 |

Category is recorded on Kalshi only; the recorder captures no category for Polymarket or Manifold, so every row from those venues is `unknown`. That is a recorder gap, not a market fact.

### By liquidity bucket

| slice | n | blocks | Brier | skill vs 50/50 | log score | base rate |
|---|---|---|---|---|---|---|
| 100-1k | 1,850 | 23 | 0.1219 | 0.512 | -0.3783 | 0.344 |
| 10k-100k | 779 | 32 | 0.1441 | 0.424 | -0.4288 | 0.403 |
| 1k-10k | 1,227 | 27 | 0.1017 | 0.593 | -0.3150 | 0.496 |
| <100 | 4,515 | 18 | 0.0937 | 0.625 | -0.3184 | 0.575 |
| >=100k | 450 | 22 | 0.1845 | 0.262 | -0.5376 | 0.387 |
| unknown | 270 | 22 | 0.1931 | 0.228 | -0.5584 | 0.541 |

Each venue's own liquidity measure, so these bands compare markets within a venue and not across venues: kalshi = open_interest (contracts); manifold = totalLiquidity; polymarket = liquidityNum (USD); predictit = none recorded

### By Polymarket recorder era

| slice | n | blocks | Brier | skill vs 50/50 | log score | base rate |
|---|---|---|---|---|---|---|
| numeric | 628 | 14 | 0.1855 | 0.258 | -0.5402 | 0.363 |
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
| kalshi | result=scalar | 27 |
| manifold | resolution=CANCEL | 23 |
| manifold | resolution=MKT | 15 |
| polymarket | outcome price not 0 or 1 | 130 |

## Cross-venue basis

Curation rule: **identical entity and identical deadline on both venues, read off both rules pages by a person; no fuzzy matching**.

`events.yaml`: 4 pair(s), 0 verified, 4 awaiting a hand check.

No verified cross-venue pair is in events.yaml, so there is no basis to measure. The file ships as a skeleton of examples marked `verified: false`; pairing is a hand check of both venues' rules pages (identical entity, identical deadline) and unverified pairs are counted here and never priced.

Awaiting verification: `fed-2026-09-hike-25bp`, `fed-2026-09-hike-any`, `govt-shutdown-2026-10-01`, `nobel-peace-2026-musk`.

## Fee models in force

Constants read 2026-09-11.

| venue | model |
|---|---|
| kalshi | taker fee = ceil to the cent of 0.07 * contracts * P * (1-P), per order; minimum one cent per order with any risk |
| polymarket | no taker fee on the CLOB; per-market overrides supported |
| predictit | 10% of profit on the winning leg, plus 5% on withdrawal |

- **kalshi:** the per-series multipliers come from Kalshi's public fee_changes feed rather than the fee-schedule PDF, which is still unreadable from here; only quadratic (taker) rows are used, so a series known only through a market-maker-program row stays on the general 0.07
- **kalshi:** the table holds the rate in force on 2026-09-16 and is flat in time; every series it changes for this archive changed before the window opened, so the replay is exact, but a mid-window change would need a dated lookup
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
