# Coherence over the archive

Generated 2026-09-18T21:41:49Z by `python -m pmlab.replay` at commit `bc4505a27d19`.

**Archive replayed:** 163 snapshots, 2026-08-23T01:18:06Z to 2026-09-18T17:43:28Z (26.7 days), realised cadence median 3.5 h / max 12.6 h.  
**Archive identity (sha256 of the blob list):** `8963d1802903d86cb2dc9233ddd309caf5fdb9bc12964e45cbdb0a451d91acc4`

Every count below is produced twice: **gross**, and **net** of the venue's own fee with the venue's own rounding. The gap between the two columns is the result.

## The one-line answer

Across 163 snapshots and 26.7 days, 462 gross ladder monotonicity inversions were read on 135 distinct strike pairs and 11 readings on 6 pairs survived the fee model; 0 PredictIt and 43 Polymarket complement violations gross, 0 and 43 net; a median 21 bucket-sum candidates per snapshot gross and 9 net, all open-universe events. The Kalshi complement identity held on 3,333,182 of 3,333,182 two-sided books.

Every inversion that survived the fee is in 3 event(s): `KXARTISTSTREAMSY-ODDMOB26DEC31`, `KXINXMINY-01JAN2027`, `KXUSDBRLAW-26SEP18`. Those are the rows to go and read by hand; everything else in this file is a count.

## Kalshi ladders

| quantity | value |
|---|---|
| ladders per snapshot (median) | 1,148 |
| ladders per snapshot (min-max, across both recorders) | 848-3,527 |
| rungs per snapshot (median) | 8,217 |
| adjacent strike pairs tested (total) | 1,803,146 |
| monotonicity inversions, gross (total) | 462 |
| ... on distinct (event, lower strike, upper strike) triples | 135 |
| monotonicity inversions, net of fee (total) | 11 |
| ... on distinct triples | 6 |
| snapshots with any gross inversion | 101 of 163 |
| negative implied mass at mids, gross (total) | 58,015 |
| ... whose magnitude exceeds two legs of fee | 23,773 |

Worst gross inversion: `KXUSDBRLAW-26SEP18` on 2026-09-17T00:37:14Z, strike 5.117 ask 0.43 against strike 5.119 bid 0.62 -- 19.0c gross, 4.0c of fee on the two legs, 15.0c net.

Recorder v1 stopped at 2,000 events (about 14,000 markets, mostly the two midterm ladder families); recorder v2 sweeps the whole open catalog (about 56,000). Pooling the two counts a different experiment twice, so they are split:

| recorder | snapshots | adjacent pairs | inversions gross | net of fee |
|---|---|---|---|---|
| v1 (2,000-event cap) | 125 | 861,844 | 293 | 0 |
| v2 (full catalog) | 38 | 941,302 | 169 | 11 |

Those 462 inversions are readings, not findings: every ladder is screened again in every snapshot, so they are 135 distinct strike pairs seen 3.42 times apiece on average, 80 of them exactly once. Nor are they spread across the catalog: they fall in 96 events.

| event | gross inversions |
|---|---|
| `KXFEDFUNDSYEAR-32JAN01` | 89 |
| `KXFEDFUNDSYEAR-37JAN01` | 52 |
| `KXFEDFUNDSYEAR-34JAN01` | 33 |
| `KXUSCPIYEAR-30FEB01` | 24 |
| `KXFEDFUNDSYEAR-31JAN01` | 19 |
| `KXFEDFUNDSYEAR-33JAN01` | 19 |
| `KXFEDFUNDSYEAR-35JAN01` | 17 |
| `KXFEDFUNDSYEAR-28JAN01` | 14 |
| `KXMDT-26DECCARDGROW` | 12 |
| `KXUSDBRLAW-26SEP18` | 11 |

The inversion screen is at the touch and is executable by construction: sell the higher strike at its bid, buy the lower at its ask. The negative-mass screen is at mids and is **not** a trade -- it says where the quoted curve is marked impossibly, which is a wider and softer statement. The two must not be read as the same number.

## Complement

| venue | pairs per snapshot (median) | gross (total) | net (total) |
|---|---|---|---|
| Polymarket (quoted outcome pair) | 929 | 43 | 43 |
| PredictIt (YES/NO asks) | 498 | 0 | 0 |
| Kalshi | not screened | - | - |

Kalshi is not screened on purpose: `no_ask == 1 - yes_bid` held on 3,333,182 of 3,333,182 two-sided books across the whole archive (0 deviations), so YES ask plus NO ask is 1 plus the spread by construction and the screen cannot fire. It is asserted as an invariant: a single deviation fails this replay.

Screened on the venue's quoted outcome-price pair, not on two asks: the complementary token's book is not in this archive (a recorder gap). A violation is an incoherent quote, not a demonstrated trade.

All 43 Polymarket violations fall in the 68 snapshots of the string-sorted era (2026-08-23 to 2026-09-01T16:44Z), when the venue served `order=liquidity` sorted as text and the recorder kept the result: thin, often already-expired rows. The 95 snapshots of the clean `liquidityNum` era carry 0. That is a statement about the recorder, not about the venue's quotes.

## Bucket sums

| quantity | value |
|---|---|
| mutually-exclusive events screened per snapshot (median) | 230 |
| candidates per snapshot, gross (median) | 21 |
| candidates per snapshot, net of fee (median) | 9 |

Most persistent candidates (snapshots in which the event was flagged):

| event | snapshots |
|---|---|
| `KXMOLDOVAPRES-28` | 163 |
| `KXNEWPOPE-70` | 163 |
| `KXNEXTSTATE-29` | 163 |
| `KXPRESMATCHUP-28NOV07` | 163 |
| `KXSENATENYD-28` | 163 |
| `KXSTATE51-29` | 163 |
| `KXTRUMPAGCOUNT-29` | 163 |
| `KXVPRESNOMR-28` | 163 |
| `KXNEXTDEPUTYAG-28JAN01` | 161 |
| `KXPRESTAIWAN-28` | 161 |

A bucket-sum candidate is NOT an arbitrage. The venue's mutually_exclusive flag promises at most one bucket settles YES, not that the listed buckets are exhaustive; the survivors on real data are open-universe events (next pope, 51st state, party nominations) whose missing 'someone else' bucket is exactly the mass that makes the asks sum below a dollar. Read the event rules before believing any row of this table.

## Calibration

Settlements read: 148,861 markets from 43 file(s) (kalshi 117,811, manifold 531, polymarket 30,342, predictit 177). Scored forecasts: 13,911 (plus 88 inferred PredictIt outcomes held out of every headline number).

Each market is scored at the **last quote at or before `settled_at - H`**, used only if it is no more than 24 h older than that cut-off. 18,965 market/horizon cells had a quote before the cut-off but only a stale one, and 5,413 had only a one-sided book; both are reported unscored rather than scored on a price nobody was quoting. The baseline everywhere is a coin flip: Brier 0.25, log score -0.6931.

**Read the `blocks` column before the `n` column.** A block is one venue's settlements on one day, and markets that resolve together do not resolve independently: a thousand forecasts spread over four settlement days is four observations of the world wearing a large `n`. The block bootstrap prices that in and the Wilson interval does not; below 3 blocks no bootstrap interval is reported at all, because resampling two blocks produces an interval about the block count rather than about the data.

### By horizon

| horizon | n | blocks | Brier | 95% block bootstrap | skill vs 50/50 | log score | base rate | median h before settlement |
|---|---|---|---|---|---|---|---|---|
| 1d (1 d) | 12,289 | 70 | 0.1101 | [0.0902, 0.1431] | 0.560 | -0.3498 | 0.479 | 26.9 |
| 1wk (7 d) | 1,622 | 49 | 0.1916 | [0.1579, 0.2156] | 0.233 | -0.5470 | 0.379 | 174.2 |
| 1mo (30 d) | 0 | 0 | - | - | - | - | - | - |
| 2mo (60 d) | 0 | 0 | - | - | - | - | - | - |

- **1mo** is empty because no settled market resolved on or after 2026-09-22T01:18:06Z, which is the earliest settlement this archive can price 1mo ahead (it opens 2026-08-23).
- **2mo** is empty because no settled market resolved on or after 2026-10-22T01:18:06Z, which is the earliest settlement this archive can price 2mo ahead (it opens 2026-08-23).

### By venue and horizon

| venue | horizon | n | blocks | Brier | skill vs 50/50 | log score | mean mid | base rate | median spread (c) |
|---|---|---|---|---|---|---|---|---|---|
| kalshi | 1d | 8,833 | 21 | 0.0867 | 0.653 | -0.2898 | 0.523 | 0.528 | 6.0 |
| kalshi | 1wk | 188 | 12 | 0.0462 | 0.815 | -0.1728 | 0.574 | 0.543 | 3.0 |
| polymarket | 1d | 3,183 | 26 | 0.1680 | 0.328 | -0.4986 | 0.351 | 0.337 | 3.0 |
| polymarket | 1wk | 1,262 | 18 | 0.2148 | 0.141 | -0.6056 | 0.438 | 0.336 | 92.0 |
| manifold | 1d | 273 | 23 | 0.1915 | 0.234 | -0.5547 | 0.501 | 0.542 | 0.0 |
| manifold | 1wk | 172 | 19 | 0.1803 | 0.279 | -0.5260 | 0.489 | 0.512 | 0.0 |

Everything below is the **1d** horizon, the shortest one this archive can fill.

### What this sample is

12,289 forecasts from 70 venue-days: kalshi 8,833, manifold 273, polymarket 3,183; Polymarket recorder era numeric 769, string_sorted 2,414.

| settlement day | forecasts |
|---|---|
| kalshi:2026-09-14 | 3,868 |
| kalshi:2026-09-15 | 1,078 |
| kalshi:2026-09-16 | 1,046 |
| kalshi:2026-09-17 | 952 |
| kalshi:2026-09-13 | 841 |
| kalshi:2026-09-12 | 496 |
| polymarket:2026-08-27 | 347 |
| polymarket:2026-08-26 | 335 |

Nothing here is a random sample of a venue's catalog. It is the set of markets that happened to resolve inside a three-week recording window, which skews hard towards short-dated sports and towards whatever the recorder's Polymarket slice contained at the time. Read every score below as a description of that set, not as a venue's calibration.

Join sanity check (not a result): markets that settled YES were quoted at a mean mid of 0.739 and markets that settled NO at 0.238. If the outcome were joined to the wrong side of the book these would be the wrong way round.

### Reliability

Wilson intervals assume the forecasts in a bin are independent. Markets that settle on the same day are not, so a block bootstrap over (venue, settlement day) blocks is reported beside them; where the two disagree, the bootstrap is the honest one.

**all** (70 settlement-day block(s))

| bin | n | mean mid | realised | Wilson 95% | bootstrap 95% |
|---|---|---|---|---|---|
| 0.0-0.1 | 2,216 | 0.041 | 0.024 | [0.018, 0.031] | [0.015, 0.037] |
| 0.1-0.2 | 1,102 | 0.150 | 0.089 | [0.074, 0.107] | [0.056, 0.138] |
| 0.2-0.3 | 1,255 | 0.247 | 0.159 | [0.140, 0.181] | [0.090, 0.257] |
| 0.3-0.4 | 866 | 0.349 | 0.290 | [0.261, 0.321] | [0.242, 0.346] |
| 0.4-0.5 | 1,469 | 0.462 | 0.385 | [0.360, 0.410] | [0.330, 0.444] |
| 0.5-0.6 | 1,006 | 0.536 | 0.581 | [0.550, 0.611] | [0.535, 0.616] |
| 0.6-0.7 | 625 | 0.648 | 0.779 | [0.745, 0.810] | [0.636, 0.864] |
| 0.7-0.8 | 648 | 0.753 | 0.901 | [0.876, 0.922] | [0.728, 0.956] |
| 0.8-0.9 | 830 | 0.834 | 0.970 | [0.956, 0.980] | [0.918, 0.984] |
| 0.9-1.0 | 2,272 | 0.969 | 0.993 | [0.988, 0.995] | [0.979, 0.999] |

**kalshi** (21 settlement-day block(s))

| bin | n | mean mid | realised | Wilson 95% | bootstrap 95% |
|---|---|---|---|---|---|
| 0.0-0.1 | 1,596 | 0.041 | 0.019 | [0.014, 0.027] | [0.011, 0.033] |
| 0.1-0.2 | 800 | 0.151 | 0.079 | [0.062, 0.099] | [0.044, 0.144] |
| 0.2-0.3 | 749 | 0.243 | 0.113 | [0.093, 0.138] | [0.051, 0.264] |
| 0.3-0.4 | 478 | 0.348 | 0.259 | [0.222, 0.301] | [0.201, 0.347] |
| 0.4-0.5 | 782 | 0.464 | 0.364 | [0.331, 0.399] | [0.268, 0.478] |
| 0.5-0.6 | 477 | 0.540 | 0.570 | [0.525, 0.614] | [0.473, 0.638] |
| 0.6-0.7 | 455 | 0.648 | 0.824 | [0.787, 0.856] | [0.626, 0.905] |
| 0.7-0.8 | 542 | 0.755 | 0.932 | [0.907, 0.950] | [0.761, 0.973] |
| 0.8-0.9 | 765 | 0.833 | 0.974 | [0.960, 0.983] | [0.919, 0.987] |
| 0.9-1.0 | 2,189 | 0.969 | 0.994 | [0.989, 0.996] | [0.980, 0.999] |

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
| 0.8-0.9 | 15 | 0.851 | 0.933 | [0.702, 0.988] | [0.789, 1.000] |
| 0.9-1.0 | 20 | 0.969 | 0.900 | [0.699, 0.972] | [0.765, 1.000] |

**polymarket** (26 settlement-day block(s))

| bin | n | mean mid | realised | Wilson 95% | bootstrap 95% |
|---|---|---|---|---|---|
| 0.0-0.1 | 600 | 0.040 | 0.037 | [0.024, 0.055] | [0.015, 0.057] |
| 0.1-0.2 | 289 | 0.147 | 0.111 | [0.080, 0.152] | [0.078, 0.146] |
| 0.2-0.3 | 489 | 0.252 | 0.227 | [0.192, 0.266] | [0.180, 0.280] |
| 0.3-0.4 | 359 | 0.349 | 0.329 | [0.282, 0.379] | [0.275, 0.372] |
| 0.4-0.5 | 641 | 0.462 | 0.392 | [0.355, 0.430] | [0.349, 0.446] |
| 0.5-0.6 | 455 | 0.530 | 0.591 | [0.545, 0.635] | [0.554, 0.629] |
| 0.6-0.7 | 144 | 0.650 | 0.653 | [0.572, 0.726] | [0.600, 0.703] |
| 0.7-0.8 | 93 | 0.740 | 0.742 | [0.645, 0.820] | [0.611, 0.838] |
| 0.8-0.9 | 50 | 0.856 | 0.920 | [0.812, 0.968] | [0.840, 1.000] |
| 0.9-1.0 | 63 | 0.962 | 0.984 | [0.915, 0.997] | [0.945, 1.000] |

### Favourite-longshot bias, on the bid and on the ask

Measured on the traded prices, never on the mid: a longshot buyer pays the ask and a favourite seller receives the bid. `bias` is realised frequency minus mean price in cents, so a negative number means that side was dearer than it was worth.

Manifold quotes a single probability rather than a book, so its bid and ask columns carry the same number; the venue split says how much of each row that is.

**Read the spread column with the bias column.** A two-sided book is not the same thing as a tradeable one: a bin whose median spread is most of a dollar is a bin of nominal quotes sitting on near-empty books, and most of its apparent bias is that fact rather than a market view. The rows are reported rather than filtered out, because picking a spread cut-off is a judgement and applying one silently would be making that judgement for the reader.

**bid**

| bin | n | mean price | realised | bias (c) | median spread (c) | Wilson 95% |
|---|---|---|---|---|---|---|
| 0.0-0.1 | 4,289 | 0.029 | 0.089 | 6.0 | 9.0 | [0.081, 0.098] |
| 0.1-0.2 | 912 | 0.140 | 0.193 | 5.3 | 4.0 | [0.169, 0.220] |
| 0.2-0.3 | 819 | 0.244 | 0.321 | 7.7 | 3.0 | [0.290, 0.354] |
| 0.3-0.4 | 778 | 0.342 | 0.500 | 15.8 | 5.0 | [0.465, 0.535] |
| 0.4-0.5 | 902 | 0.448 | 0.596 | 14.9 | 3.0 | [0.564, 0.628] |
| 0.5-0.6 | 887 | 0.541 | 0.710 | 16.9 | 4.0 | [0.680, 0.739] |
| 0.6-0.7 | 810 | 0.634 | 0.853 | 21.9 | 32.0 | [0.827, 0.876] |
| 0.7-0.8 | 411 | 0.740 | 0.888 | 14.8 | 10.0 | [0.854, 0.915] |
| 0.8-0.9 | 603 | 0.831 | 0.959 | 12.8 | 13.0 | [0.940, 0.972] |
| 0.9-1.0 | 1,878 | 0.969 | 0.995 | 2.7 | 1.0 | [0.991, 0.997] |

**ask**

| bin | n | mean price | realised | bias (c) | median spread (c) | Wilson 95% |
|---|---|---|---|---|---|---|
| 0.0-0.1 | 1,852 | 0.044 | 0.017 | -2.7 | 1.0 | [0.012, 0.024] |
| 0.1-0.2 | 923 | 0.138 | 0.094 | -4.4 | 4.0 | [0.077, 0.115] |
| 0.2-0.3 | 803 | 0.246 | 0.171 | -7.5 | 3.0 | [0.146, 0.198] |
| 0.3-0.4 | 903 | 0.346 | 0.219 | -12.7 | 9.0 | [0.194, 0.247] |
| 0.4-0.5 | 1,113 | 0.446 | 0.304 | -14.3 | 7.0 | [0.277, 0.331] |
| 0.5-0.6 | 962 | 0.539 | 0.440 | -9.9 | 4.0 | [0.409, 0.471] |
| 0.6-0.7 | 531 | 0.640 | 0.552 | -8.9 | 7.0 | [0.509, 0.594] |
| 0.7-0.8 | 469 | 0.744 | 0.652 | -9.2 | 12.0 | [0.608, 0.694] |
| 0.8-0.9 | 508 | 0.847 | 0.787 | -6.0 | 19.5 | [0.750, 0.821] |
| 0.9-1.0 | 4,225 | 0.983 | 0.868 | -11.5 | 17.0 | [0.858, 0.878] |

### By category

| slice | n | blocks | Brier | skill vs 50/50 | log score | base rate |
|---|---|---|---|---|---|---|
| Climate and Weather | 1,483 | 5 | 0.0913 | 0.635 | -0.2932 | 0.195 |
| Commodities | 895 | 5 | 0.0944 | 0.623 | -0.3019 | 0.582 |
| Companies | 1 | 1 | 0.0009 | 0.996 | -0.0305 | 1.000 |
| Crypto | 540 | 5 | 0.0682 | 0.727 | -0.2264 | 0.787 |
| Economics | 376 | 6 | 0.0721 | 0.711 | -0.2345 | 0.620 |
| Elections | 288 | 15 | 0.0193 | 0.923 | -0.0793 | 0.875 |
| Entertainment | 1,010 | 9 | 0.1146 | 0.542 | -0.3543 | 0.445 |
| Financials | 2,838 | 6 | 0.0629 | 0.748 | -0.2504 | 0.679 |
| Mentions | 448 | 6 | 0.1530 | 0.388 | -0.4557 | 0.402 |
| Politics | 124 | 10 | 0.0777 | 0.689 | -0.2670 | 0.411 |
| Science and Technology | 79 | 4 | 0.0471 | 0.811 | -0.1808 | 0.608 |
| Sports | 751 | 11 | 0.1338 | 0.465 | -0.4013 | 0.379 |
| unknown | 3,456 | 49 | 0.1699 | 0.320 | -0.5030 | 0.354 |

Category is recorded on Kalshi only; the recorder captures no category for Polymarket or Manifold, so every row from those venues is `unknown`. That is a recorder gap, not a market fact.

### By liquidity bucket

| slice | n | blocks | Brier | skill vs 50/50 | log score | base rate |
|---|---|---|---|---|---|---|
| 100-1k | 2,586 | 26 | 0.1189 | 0.524 | -0.3713 | 0.360 |
| 10k-100k | 1,097 | 38 | 0.1332 | 0.467 | -0.3985 | 0.397 |
| 1k-10k | 1,842 | 30 | 0.0974 | 0.610 | -0.3055 | 0.472 |
| <100 | 5,953 | 21 | 0.0965 | 0.614 | -0.3210 | 0.550 |
| >=100k | 539 | 28 | 0.1742 | 0.303 | -0.5118 | 0.408 |
| unknown | 272 | 22 | 0.1917 | 0.233 | -0.5552 | 0.544 |

Each venue's own liquidity measure, so these bands compare markets within a venue and not across venues: kalshi = open_interest (contracts); manifold = totalLiquidity; polymarket = liquidityNum (USD); predictit = none recorded

### By Polymarket recorder era

| slice | n | blocks | Brier | skill vs 50/50 | log score | base rate |
|---|---|---|---|---|---|---|
| numeric | 769 | 17 | 0.1804 | 0.278 | -0.5272 | 0.382 |
| string_sorted | 2,414 | 11 | 0.1641 | 0.344 | -0.4895 | 0.323 |

The string-sorted era is the nine days the venue served `order=liquidity` as text and the recorder kept the result.

### Inferred outcomes (excluded from every number above)

PredictIt outcomes are inferred from the last trade of a contract that left the public feed, not observed. These scores are reported so the inference can be judged, and are excluded from every headline number.

| horizon | n | Brier | skill vs 50/50 |
|---|---|---|---|
| 1d | 35 | 0.1272 | 0.491 |
| 1wk | 53 | 0.1548 | 0.381 |

Settlement records read but not scoreable:

| venue | reason | records |
|---|---|---|
| kalshi | result=scalar | 53 |
| manifold | resolution=CANCEL | 23 |
| manifold | resolution=MKT | 16 |
| polymarket | outcome price not 0 or 1 | 150 |

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
