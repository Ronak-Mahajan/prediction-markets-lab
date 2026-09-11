"""Per-blob cache of the coherence screens, for the incremental replay.

The replay re-reads the whole archive on every run, and the archive only
grows. Measured on 2026-09-11 on the recording machine: a recorder-v1
snapshot (14,549 Kalshi markets) costs about 0.25 s to load and 0.17 s to
screen; a recorder-v2 snapshot (56,625 markets) costs 1.85 s to load and
0.98 s to screen. At the cron's realised cadence that is a job whose
runtime grows by about twenty seconds a day, and the analysis workflow has
a ten-minute budget.

What this cache removes, and what it cannot
-------------------------------------------

A snapshot's *screens* depend on nothing but that snapshot's bytes. Ladder
inversions, complement violations and bucket sums are a pure function of
one blob, so once a blob's sha256 has been seen, its row in
``results/timeseries.csv`` and the worst cases behind it can be replayed
from here instead of recomputed. That is the 0.98 s.

The *settlement join* is not a pure function of one blob: a market that
settles tomorrow is scored against a quote recorded weeks ago, so a
snapshot's contribution changes as settlements arrive. Skipping a blob
because its screens are cached would silently drop quotes from the
calibration tables. So every blob is still read and decoded, and
:func:`pmlab.archive.snapshot_from_raw` is handed the join's key set so
that only the rows the join can use are coerced -- a few hundred of the
56,000 markets in a v2 blob. That is most of the 1.85 s.

What is left is the gzip and JSON decode of every blob, about 0.8 s for a
v2 snapshot, which no cache keyed on blob identity can avoid: the identity
*is* the bytes. Removing that needs a per-blob quote index written once
and read instead of the blob, which is the next thing to build when this
job approaches its budget again. The saving here is roughly a third of the
run and, more to the point, it makes the growth rate the decode cost
rather than the decode-plus-screen cost.

Correctness
-----------

* An entry is used only when the blob's sha256 matches. Different bytes
  are a different snapshot, always.
* The whole cache is discarded when :func:`code_fingerprint` changes, so a
  change to any module in this package re-derives every number rather than
  serving one produced by code that no longer exists. The fingerprint
  covers the whole package, which over-invalidates (editing this
  docstring drops the cache) in the direction that cannot publish a stale
  number.
* A missing, unreadable or stale cache is a cache miss, never an error:
  the replay then does exactly what it did before this file existed.
* ``tests/test_analysis.py`` asserts that a cached replay and a cold one
  produce byte-identical ``timeseries.csv`` and ``summary.json``.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

CACHE_SCHEMA = 1

#: Where CI keeps it. Gitignored: this is a build cache, not a result, and
#: committing it would put a megabyte of derived state in the history every
#: run. GitHub Actions restores it with actions/cache.
DEFAULT_CACHE = ".replaycache/replay.json.gz"


def code_fingerprint() -> str:
    """sha256 over every ``.py`` in this package, by name then bytes."""
    h = hashlib.sha256()
    for p in sorted(Path(__file__).resolve().parent.glob("*.py")):
        h.update(p.name.encode())
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


class ReplayCache:
    """``{snapshot key: {sha256, row, detail}}``, keyed on the blob's bytes.

    The snapshot key is ``YYYYMMDD/HHMMZ.json.gz``, the same string the
    timeseries writes in its ``path`` column. Two data roots can in
    principle offer the same key for different bytes; the sha256 check
    makes that a miss rather than a wrong answer.
    """

    def __init__(self, fingerprint: str | None = None,
                 entries: dict | None = None):
        self.fingerprint = fingerprint or code_fingerprint()
        self.entries: dict[str, dict] = entries or {}
        self.hits = 0
        self.misses = 0
        self.discarded_reason = ""

    # ------------------------------------------------------------ load/save

    @classmethod
    def load(cls, path: str | Path) -> "ReplayCache":
        """Read a cache, or return an empty one and say why it was empty."""
        fp = code_fingerprint()
        p = Path(path)
        if not p.is_file():
            c = cls(fp)
            c.discarded_reason = "no cache file yet"
            return c
        try:
            opener = gzip.open if p.suffix == ".gz" else open
            with opener(p, "rt", encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError, EOFError) as exc:
            c = cls(fp)
            c.discarded_reason = f"cache unreadable ({exc!r})"
            return c
        if doc.get("schema") != CACHE_SCHEMA:
            c = cls(fp)
            c.discarded_reason = "cache written by a different cache schema"
            return c
        if doc.get("code_fingerprint") != fp:
            c = cls(fp)
            c.discarded_reason = ("the analysis code changed since this cache "
                                  "was written; every snapshot is re-screened")
            return c
        entries = doc.get("entries")
        if not isinstance(entries, dict):
            c = cls(fp)
            c.discarded_reason = "cache has no entries map"
            return c
        return cls(fp, entries)

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        doc = {"schema": CACHE_SCHEMA, "code_fingerprint": self.fingerprint,
               "entries": self.entries}
        payload = json.dumps(doc, separators=(",", ":"),
                             sort_keys=True).encode("utf-8")
        if p.suffix == ".gz":
            # gzip.open cannot set mtime, and a wall-clock stamp inside the
            # member header makes the same cache content different bytes on
            # every run. GzipFile with mtime=0 keeps it reproducible.
            with open(p, "wb") as raw:
                with gzip.GzipFile(filename="", mode="wb", fileobj=raw,
                                   mtime=0) as gz:
                    gz.write(payload)
        else:
            p.write_bytes(payload)
        return p

    # ------------------------------------------------------------- get/put

    def get(self, key: str, sha256: str) -> dict | None:
        e = self.entries.get(key)
        if not isinstance(e, dict) or e.get("sha256") != sha256:
            self.misses += 1
            return None
        row, detail = e.get("row"), e.get("detail")
        if not isinstance(row, dict) or not isinstance(detail, dict):
            self.misses += 1
            return None
        self.hits += 1
        return {"row": row, "detail": detail}

    def put(self, key: str, sha256: str, row: dict, detail: dict) -> None:
        self.entries[key] = {"sha256": sha256, "row": row, "detail": detail}

    def prune(self, live_keys: set[str]) -> int:
        """Drop entries for blobs no longer under any replayed root."""
        dead = [k for k in self.entries if k not in live_keys]
        for k in dead:
            del self.entries[k]
        return len(dead)

    def describe(self) -> str:
        why = f" ({self.discarded_reason})" if self.discarded_reason else ""
        return (f"cache: {self.hits} hit(s), {self.misses} miss(es), "
                f"{len(self.entries)} entr(ies){why}")
