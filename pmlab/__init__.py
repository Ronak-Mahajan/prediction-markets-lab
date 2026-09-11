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
- ``pmlab.replay``      the CLI that runs all of it over every snapshot and
                        writes ``results/``

Everything here is standard library except the replay's optional
matplotlib figures (``python -m pmlab.replay --no-plots`` skips them).
"""
