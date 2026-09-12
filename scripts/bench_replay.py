"""Measure what the incremental replay actually saves, and print the numbers.

    python scripts/bench_replay.py                   # per-snapshot costs only
    python scripts/bench_replay.py --end-to-end      # also the whole archive

The README quotes two performance numbers: the cost of a full replay with
and without ``--cache``, and the per-snapshot load/screen/decode split
that says *why* the cache saves what it saves. This script is the code
those numbers ship with, so a reader can re-run it rather than take them
on trust, and the owner can re-measure when the archive has grown.

Why it alternates
-----------------

The first measurement of this was wrong in a way worth keeping a note
about. A full replay was timed once with no cache (111 s) and once with
``--cache`` (36 s), and the difference was published as the cache's
saving. It was not: the first run had just pulled 88 MB of gzip off a
cold page cache and the second read it from RAM, and the 36 s run had
*zero* cache hits -- it was the run that populated the cache. Almost the
whole gap was the operating system, not this repository's code.

So: every blob is read once before timing starts to warm the page cache,
the two configurations are interleaved rather than run in blocks, and the
report is a median with its range, because on the recording machine an
identical no-cache replay varies by about 30% run to run. A single
number would imply a precision the machine does not have.

The cached configuration is always timed on a *warm* cache -- one that
has already been written by a previous run -- because that is the state
CI is in on every run after the first.
"""
from __future__ import annotations

import argparse
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pmlab import replay as replay_mod                        # noqa: E402
from pmlab.archive import (load_snapshot, load_snapshot_from_blob,  # noqa: E402
                           read_blob, snapshot_paths)

DEFAULT_ROOTS = ("data", "archive/data")

#: The same settlement roots `.github/workflows/analysis.yml` passes. The
#: settlement join is a real part of what a CI run costs and it is the part
#: the cache deliberately does not skip, so timing without it would flatter
#: the cache. Roots that do not exist are dropped and the run is then a
#: zero-settlement one, which is what a fresh clone measures.
DEFAULT_SETTLEMENTS = ("archive/settlements", "settlements")


def _median_range(xs: list[float]) -> str:
    return (f"{statistics.median(xs):6.2f} s   "
            f"(n={len(xs)}, {min(xs):.2f}-{max(xs):.2f})")


def warm_page_cache(paths: list[Path]) -> int:
    total = 0
    for p in paths:
        total += len(p.read_bytes())
    return total


# --------------------------------------------------------------------------
# per snapshot: where the time goes
# --------------------------------------------------------------------------

def per_snapshot(paths: list[Path], reps: int) -> None:
    """Load, screen and decode-only cost for the newest blob of each schema.

    ``decode-only`` is a filtered load with an empty keep set: it does the
    gzip and JSON work and builds no rows, so it is the floor the cache
    cannot go below, because a blob's identity is its bytes.
    """
    newest: dict[int, Path] = {}
    for p in paths:
        schema = load_snapshot(p).schema
        newest[schema] = p                       # paths are in time order
    if not newest:
        print("no snapshots found"); return

    print("Per snapshot, newest blob of each recorder generation")
    print(f"  {'':<12} {'markets':>9} {'blob':>9} {'load':>8} "
          f"{'screen':>8} {'decode':>8}")
    for schema in sorted(newest):
        p = newest[schema]
        snap = load_snapshot(p)
        raw = read_blob(p)

        def t(fn) -> float:
            xs = []
            for _ in range(reps):
                t0 = time.perf_counter(); fn(); xs.append(time.perf_counter() - t0)
            return statistics.median(xs)

        load_s = t(lambda: load_snapshot(p))
        screen_s = t(lambda: replay_mod.replay_one(p, snap=snap))
        decode_s = t(lambda: load_snapshot_from_blob(p, raw, keep={}))
        print(f"  v{schema} {p.parent.name:<9} {len(snap.kalshi):>9,} "
              f"{len(raw)/1e6:>7.2f} MB {load_s:>7.2f}s {screen_s:>7.2f}s "
              f"{decode_s:>7.2f}s")
    print()
    print("  The cache removes the screen column and nothing else: the "
          "settlement join")
    print("  needs every blob decoded, so load stays and decode is the floor.")


# --------------------------------------------------------------------------
# end to end: what a CI run costs
# --------------------------------------------------------------------------

def end_to_end(roots: tuple[str, ...], settlements: tuple[str, ...],
               reps: int) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="pmlab-bench-"))
    out, cache = tmp / "out", tmp / "replay.json.gz"
    base = [sys.executable, "-m", "pmlab.replay", "--roots", *roots,
            "--settlements", *(settlements or (str(tmp / "no-settlements"),)),
            "--events", "events.yaml", "--out", str(out), "--quiet"]

    def run(args: list[str]) -> float:
        t0 = time.perf_counter()
        r = subprocess.run(base + args, capture_output=True, text=True,
                           cwd=str(ROOT))
        if r.returncode != 0:
            raise SystemExit(f"replay failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
        return time.perf_counter() - t0

    run(["--cache", str(cache)])                  # populate, not timed
    cold: list[float] = []
    warm: list[float] = []
    for i in range(reps):
        cold.append(run([]))                      # interleaved, not blocked
        warm.append(run(["--cache", str(cache)]))
        print(f"  rep {i+1}: no cache {cold[-1]:6.2f} s | cached {warm[-1]:6.2f} s",
              flush=True)
    mc, mw = statistics.median(cold), statistics.median(warm)
    print()
    print(f"  no cache   {_median_range(cold)}")
    print(f"  --cache    {_median_range(warm)}")
    print(f"  => {mc / mw:.1f}x, {100 * (1 - mw / mc):.0f}% of the wall clock removed")
    for p in sorted(out.glob("*")):
        try:
            p.unlink()
        except OSError:
            pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--roots", nargs="+", default=list(DEFAULT_ROOTS))
    ap.add_argument("--settlements", nargs="+", default=list(DEFAULT_SETTLEMENTS))
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--end-to-end", action="store_true",
                    help="also time a full replay with and without --cache "
                         "(slow: 2 * reps + 1 full replays)")
    a = ap.parse_args(argv)

    roots = tuple(r for r in a.roots if (ROOT / r).is_dir())
    if not roots:
        print(f"none of {a.roots} exist; nothing to measure")
        return 0
    # Absolute for this process, relative for the subprocess (which runs with
    # cwd=ROOT). Resolving here rather than chdir-ing keeps the benchmark
    # free of a global side effect, so a test can call main() safely.
    paths = snapshot_paths(*(str(ROOT / r) for r in roots))
    if not paths:
        print("no snapshots under " + ", ".join(roots))
        return 0

    settlements = tuple(s for s in a.settlements if (ROOT / s).is_dir())
    nbytes = warm_page_cache(paths)
    print(f"{len(paths)} snapshots under {', '.join(roots)}; "
          f"{nbytes/1e6:.1f} MB read once to warm the page cache")
    print(f"settlement roots: {', '.join(settlements) if settlements else 'none'}")
    print()
    per_snapshot(paths, a.reps)
    if a.end_to_end:
        print()
        print("Whole archive, interleaved so machine drift hits both equally")
        end_to_end(roots, settlements, a.reps)
    else:
        print()
        print("(--end-to-end also times a full replay with and without the cache)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
