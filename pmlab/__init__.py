"""pmlab: the measurement engine behind prediction-markets-lab.

Recording and storage:

- ``pmlab.archive``     load any snapshot (schema 1 or 2, either Polymarket
                        era) into typed, float-coerced venue rows
- ``pmlab.manifest``    the per-blob sha256 manifest on the data branch
- ``pmlab.sparse``      which snapshot days a job still has to fetch

Analysis (Phase 2). Every screen reports gross AND net of the venue's own
fee with the venue's own rounding; the gap between the two is the result:

- ``pmlab.fees``        dated per-venue fee constants and the rounding rule
- ``pmlab.ladders``     threshold ladders, implied P(>= s), monotonicity
                        and negative-mass screens
- ``pmlab.complement``  Polymarket and PredictIt complement screens, plus
                        the Kalshi ``no_ask == 1 - yes_bid`` invariant that
                        is asserted rather than reported
- ``pmlab.buckets``     mutually-exclusive bucket sums, with the
                        open-universe caveat attached to every number

Analysis (Phase 3). These ask whether the prices were *right* rather than
whether they were coherent, so both need something outside the quotes --
settlements for one, a person's judgement for the other -- and both are
built to run cleanly and report why when that thing is not there yet:

- ``pmlab.calibration`` settlements joined to the last quote at each
                        horizon before settlement; Brier and log score
                        against a 50/50 baseline, reliability curves with
                        Wilson and block-bootstrap intervals, and
                        favourite-longshot bias on the bid and on the ask
                        separately, sliced by venue, category, horizon and
                        liquidity
- ``pmlab.basis``       the hand-curated ``events.yaml`` map of events that
                        genuinely trade on two venues, and the fee-adjusted
                        basis distribution and half-life per pair

- ``pmlab.replay``      the CLI that runs all of it over every snapshot in
                        one pass and writes ``results/``

Everything here is standard library except the replay's optional
matplotlib figures (``python -m pmlab.replay --no-plots`` skips them) and
``pmlab.basis``'s YAML reader, whose absence is reported rather than
silently treated as an empty map.
"""
