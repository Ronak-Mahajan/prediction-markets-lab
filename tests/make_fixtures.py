"""Cut a real snapshot down to ~20 rows per venue for the schema tests.

    python tests/make_fixtures.py data/20260823/0118Z.json.gz tests/fixtures/v1_20260823_0118Z.json.gz
    python tests/make_fixtures.py data/20260910/1630Z.json.gz tests/fixtures/v1_20260910_1630Z.json.gz
    python tests/make_fixtures.py <a v2 snapshot>            tests/fixtures/v2_20260911_0714Z.json.gz

The document structure and every field name are kept exactly as the
recorder wrote them, so a fixture exercises the real field shapes of that
day. Only the number of rows shrinks.

Kalshi events are not taken in catalog order: the head of the v2 sweep is
esports games with no quotes at all, which would make a fixture that
silently skips the complement-identity and strike-field assertions. The
selector below walks the events once and keeps the first event matching
each coverage rule (a two-sided book, a floor_strike, a cap_strike, an
unquoted market), then tops up in catalog order. Deterministic, so
re-cutting the same snapshot gives the same fixture.
"""
from __future__ import annotations

import gzip
import json
import sys

N = 20
N_MARKETS_PER_EVENT = 8


def _f(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _two_sided(m: dict) -> bool:
    return _f(m.get("yes_bid_dollars")) > 0 and _f(m.get("yes_ask_dollars")) > 0


RULES = (
    ("two_sided", _two_sided),
    ("floor_strike", lambda m: m.get("floor_strike") is not None and _two_sided(m)),
    ("cap_strike", lambda m: m.get("cap_strike") is not None),
    ("unquoted", lambda m: m.get("quoted") is False),
)


def pick_kalshi(events: list[dict]) -> list[dict]:
    chosen: list[int] = []
    for _name, pred in RULES:
        for i, ev in enumerate(events):
            if i in chosen:
                continue
            if any(pred(m) for m in ev.get("markets", [])):
                chosen.append(i)
                break
    for i in range(len(events)):                     # top up in catalog order
        if sum(len(events[j].get("markets", [])[:N_MARKETS_PER_EVENT]) for j in chosen) >= N:
            break
        if i not in chosen:
            chosen.append(i)
    out = []
    for i in sorted(chosen):
        ev = dict(events[i])
        ms = ev.get("markets", [])
        # keep the markets that matched a rule first, then catalog order
        keep = [m for m in ms if any(p(m) for _n, p in RULES)]
        keep += [m for m in ms if m not in keep]
        ev["markets"] = keep[:N_MARKETS_PER_EVENT]
        out.append(ev)
    return out


def trim(doc: dict) -> dict:
    out = {k: v for k, v in doc.items() if k != "venues"}
    venues = doc.get("venues", {})
    tv: dict = {}
    if "kalshi" in venues:
        tv["kalshi"] = pick_kalshi(venues["kalshi"])
    if "polymarket" in venues:
        tv["polymarket"] = venues["polymarket"][:N]
    if "predictit" in venues:
        tv["predictit"] = venues["predictit"][:3]
    if "manifold" in venues:
        tv["manifold"] = venues["manifold"][:N]
    out["venues"] = tv
    return out


def main(src: str, dst: str) -> None:
    with gzip.open(src, "rt", encoding="utf-8") as fh:
        doc = json.load(fh)
    with gzip.open(dst, "wt", encoding="utf-8") as fh:
        json.dump(trim(doc), fh, separators=(",", ":"))
    print("wrote", dst)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
