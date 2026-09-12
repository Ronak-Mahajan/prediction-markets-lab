"""Fail the build when a number in README.md drifts from results/summary.json.

    python scripts/check_readme.py              # verify (exit 1 on drift)
    python scripts/check_readme.py --write      # rewrite the numbers in place

This is the guard against the failure mode the repo already had: the
README said "44 ladders, zero inversions", the number was measured once by
hand on 2026-08-23, and by 2026-09-10 the same regex gave 27 while nobody
noticed. Prose that quotes a measurement has to be tied to the file the
measurement lives in, or it becomes a claim about the past written in the
present tense.

The tie is a marker. Any number in README.md may be followed by an HTML
comment naming a dotted path into ``results/summary.json``:

    ...1,114 <!-- results:ladders.median_per_snapshot --> ladders...

The comment is invisible in rendered Markdown. The checker reads the
number immediately in front of each marker, looks the key up, and
complains if they disagree. Formatting is preserved: if the prose writes
``1,114`` the value is compared (and rewritten) with thousands separators,
and if it writes ``3.3`` the comparison is to one decimal place, so a
README may round as long as it rounds honestly.

``--write`` is how the analysis workflow keeps the two in sync as the
archive grows: regenerate results, rewrite the markers, commit both, then
run the plain check as a verification step. A human editing a number by
hand in a pull request still fails, which is the point.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

#: A number (optionally with thousands separators and decimals, optionally
#: signed) immediately followed by a results marker.
MARKER = re.compile(
    r"(?P<num>-?\d[\d,]*(?:\.\d+)?)(?P<gap>\s*)<!--\s*results:(?P<key>[A-Za-z0-9_.]+)\s*-->")


def lookup(summary: dict, key: str):
    """Dotted path into summary.json; raises KeyError naming the bad segment."""
    node = summary
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(f"{key} (no '{part}')")
        node = node[part]
    return node


def decimals_of(sample: str) -> int:
    return len(sample.split(".")[1]) if "." in sample else 0


def format_like(value: float, sample: str) -> str:
    """Render ``value`` the way ``sample`` is written (separators, decimals)."""
    if value is None:
        return "n/a"
    decimals = decimals_of(sample)
    grouped = "," in sample
    if decimals == 0:
        v = round(float(value))
        return f"{v:,}" if grouped else str(v)
    return (f"{float(value):,.{decimals}f}" if grouped
            else f"{float(value):.{decimals}f}")


def agrees(value: float, sample: str) -> bool:
    """Is the number written in the prose a faithful rounding of ``value``?

    Not a string comparison: 19.15 may be written 19.1 or 19.2 and both are
    honest at one decimal place, and which one Python's formatter picks
    depends on the binary representation rather than on anything a reader
    cares about. Anything more than half a unit in the last written place
    away is drift.
    """
    try:
        written = float(sample.replace(",", ""))
    except ValueError:
        return False
    tol = 0.5 * (10 ** -decimals_of(sample))
    return abs(written - float(value)) <= tol + 1e-12


def check(readme: Path, summary_path: Path, write: bool = False
          ) -> tuple[int, list[str], str]:
    """(markers checked, problems, new text). ``new text`` differs only with drift."""
    text = readme.read_text(encoding="utf-8")
    with open(summary_path, encoding="utf-8") as fh:
        summary = json.load(fh)
    problems: list[str] = []
    checked = 0

    def repl(m: re.Match) -> str:
        nonlocal checked
        checked += 1
        key, written = m.group("key"), m.group("num")
        try:
            value = lookup(summary, key)
        except KeyError as exc:
            problems.append(f"{readme.name}: unknown results key {exc}")
            return m.group(0)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            problems.append(
                f"{readme.name}: results:{key} is {type(value).__name__}, "
                f"not a number; markers may only tag numeric values")
            return m.group(0)
        want = format_like(value, written)
        if not agrees(value, written):
            problems.append(
                f"{readme.name}: results:{key} says {want} but the README "
                f"says {written}")
            if write:
                return f"{want}{m.group('gap')}<!-- results:{key} -->"
        return m.group(0)

    new_text = MARKER.sub(repl, text)
    if write and problems:
        # Drift that --write repaired is not a problem any more; keys that do
        # not exist still are.
        problems = [p for p in problems if "unknown results key" in p
                    or "not a number" in p]
    return checked, problems, new_text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--readme", default="README.md")
    ap.add_argument("--summary", default="results/summary.json")
    ap.add_argument("--write", action="store_true",
                    help="rewrite drifted numbers instead of failing")
    ap.add_argument("--min-markers", type=int, default=1,
                    help="fail if the README carries fewer markers than this; "
                         "guards against someone deleting the tie itself")
    a = ap.parse_args(argv)

    readme, summary = Path(a.readme), Path(a.summary)
    if not summary.exists():
        # Before the first replay there is nothing to drift from. That is the
        # ordinary state of a fresh clone, not a failure.
        print(f"{summary} does not exist yet; nothing to check")
        return 0
    if not readme.exists():
        print(f"{readme} does not exist", file=sys.stderr)
        return 1

    checked, problems, new_text = check(readme, summary, write=a.write)
    if a.write:
        old = readme.read_text(encoding="utf-8")
        if new_text != old:
            readme.write_text(new_text, encoding="utf-8", newline="\n")
            print(f"{readme}: rewrote drifted numbers")
        else:
            print(f"{readme}: {checked} marker(s) already in sync")
    for p in problems:
        print(p, file=sys.stderr)
    if checked < a.min_markers:
        print(f"{readme}: {checked} results marker(s), expected at least "
              f"{a.min_markers}", file=sys.stderr)
        return 1
    if problems:
        print(f"{len(problems)} README number(s) disagree with {summary}. "
              f"Regenerate with 'python -m pmlab.replay' and re-run this with "
              f"--write; never edit a tagged number by hand.", file=sys.stderr)
        return 1
    print(f"{readme}: {checked} number(s) match {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
