# prediction-markets-lab: data branch

Orphan branch holding the snapshot archive recorded by
`.github/workflows/record.yml` from the day this branch was created,
and the settlement records written by `settle.yml`. The first 117
snapshots (2026-08-23 to 2026-09-11) live under `data/` on `main` and
were never moved; readers combine both roots via `pmlab.archive`.

- `data/YYYYMMDD/HHMMZ.json.gz`  one schema-2 snapshot per recorder run
- `manifest.json`                sha256 and size per blob, snapshot count, archive identity
- `settlements/<venue>/*.jsonl`  resolutions captured by `settle.py`

No code lives here. Do not rewrite this branch's history.
