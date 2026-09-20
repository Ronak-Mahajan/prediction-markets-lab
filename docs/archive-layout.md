# How the archive is laid out in git

A note for anyone reading commit metadata rather than snapshot contents.

`data/` on `main` holds the recorder-v1 snapshots. The code and the first
65 of those snapshots were committed in one batch on 2026-08-31 and then
laid out as one commit per snapshot, so a per-snapshot commit timestamp
dated before 2026-08-31 is reconstructed rather than original. The first
seven snapshots on 2026-08-23 were recorded locally, before the first
Actions run.

The timestamp every study uses is not the commit's. Each snapshot carries
its own `t` field, written by the recorder at the moment of the request
and never altered, and `pmlab.archive` reads that.

From recorder v2 onward, snapshots are appended to the orphan `data`
branch, one commit per run, under `data/YYYYMMDD/HHMMZ.json.gz` with a
`manifest.json` carrying the sha256 and size of every blob plus an
archive identity hash.
