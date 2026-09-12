"""The four workflows, checked as data rather than read by eye.

Three of them push. Two write generated files (results, failure logs) to
whatever branch triggered them, and two write snapshots and settlements to
the orphan ``data`` branch. None of them may write to ``main``: the cron
runs from ``main``, so a workflow that pushed there would rewrite the
branch it is launched from, and the repository's own rule is that the 117
committed snapshots and the code on ``main`` change only by pull request.

The other thing pinned here is that a job with nothing to do exits green.
Both the settle job and the analysis job run before the ``data`` branch
exists, and "no data yet" is the ordinary state of a fresh branch, not a
failure -- a red build for it trains the owner to ignore red builds.
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted(glob.glob(str(ROOT / ".github" / "workflows" / "*.yml")))

sys.path.insert(0, str(ROOT))


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def steps(doc: dict):
    for job, spec in (doc.get("jobs") or {}).items():
        for step in spec.get("steps", []) or []:
            yield job, step


def test_there_are_workflows_to_check():
    assert len(WORKFLOWS) == 4, WORKFLOWS


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: Path(p).name)
def test_workflow_parses_and_names_a_job(path):
    doc = load(path)
    assert doc.get("jobs"), path
    for job, spec in doc["jobs"].items():
        assert spec.get("runs-on"), f"{path}:{job}"
        assert spec.get("steps"), f"{path}:{job}"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: Path(p).name)
def test_no_step_can_push_to_main(path):
    """A push is allowed only to the orphan data branch, or from a step that
    has already excluded main with an `if`."""
    doc = load(path)
    pushes = 0
    for job, step in steps(doc):
        run = step.get("run") or ""
        if "git push origin" not in run:
            continue
        pushes += 1
        to_data = "HEAD:data" in run
        guarded = "refs/heads/main" in str(step.get("if", ""))
        assert to_data or guarded, (
            f"{Path(path).name}:{job}:{step.get('name')!r} pushes without "
            f"excluding main")
    if Path(path).name != "ci.yml":
        assert pushes, f"{path} was expected to push somewhere"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: Path(p).name)
def test_a_writing_workflow_asks_for_write_permission(path):
    doc = load(path)
    assert (doc.get("permissions") or {}).get("contents") == "write", path


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: Path(p).name)
def test_every_job_has_a_timeout(path):
    """An unbounded job burns the account's minutes when a venue hangs."""
    doc = load(path)
    for job, spec in doc["jobs"].items():
        assert spec.get("timeout-minutes"), f"{path}:{job}"


def test_the_jobs_that_write_a_failure_log_exclude_main():
    """The write-back is the only way a CI failure is readable without a
    token, and it must never land on main."""
    seen = 0
    for path in WORKFLOWS:
        for job, step in steps(load(path)):
            name = str(step.get("name") or "")
            if "failure log" not in name:
                continue
            seen += 1
            cond = str(step.get("if", ""))
            assert "failure()" in cond, f"{path}:{name}"
            assert "refs/heads/main" in cond, f"{path}:{name}"
    assert seen == 4, seen


def test_the_data_branch_being_absent_is_green_not_red():
    """settle.yml and analysis.yml both run before the recorder has created
    the data branch. Both must probe for it and carry on."""
    for name in ("settle.yml", "analysis.yml"):
        doc = load(str(ROOT / ".github" / "workflows" / name))
        probes = [s for _, s in steps(doc) if s.get("id") == "probe"]
        assert probes, name
        assert "exists=false" in probes[0]["run"], name
        gated = [s for _, s in steps(doc)
                 if "steps.probe.outputs.exists" in str(s.get("if", ""))]
        assert gated, name


def test_the_analysis_job_verifies_the_readme_after_syncing_it():
    """--write repairs drift; the run that follows is the gate. If the order
    ever flips, nothing checks the numbers."""
    doc = load(str(ROOT / ".github" / "workflows" / "analysis.yml"))
    order = [s.get("name") for _, s in steps(doc)]
    sync = order.index("sync README numbers to results")
    gate = order.index("README numbers match results")
    assert sync < gate
    gate_step = [s for _, s in steps(doc)
                 if s.get("name") == "README numbers match results"][0]
    assert "--write" not in gate_step["run"]
    assert "--min-markers" in gate_step["run"]


def test_the_ci_job_never_runs_the_readme_checker_with_write():
    """ci.yml's pytest is the only gate against a hand-edited tagged number,
    because the analysis job syncs before it verifies."""
    doc = load(str(ROOT / ".github" / "workflows" / "ci.yml"))
    for _, step in steps(doc):
        assert "--write" not in (step.get("run") or "")


def test_the_replay_uses_the_screen_cache_and_the_key_tracks_the_code():
    """A cache key that does not move with the code would serve a row
    produced by code that no longer exists. pmlab/cache.py checks its own
    fingerprint too, so this is the second of two locks."""
    doc = load(str(ROOT / ".github" / "workflows" / "analysis.yml"))
    replay = [s for _, s in steps(doc) if s.get("name") == "replay the archive"]
    assert replay and "--cache" in replay[0]["run"]
    cache = [s for _, s in steps(doc) if str(s.get("uses", "")).startswith(
        "actions/cache")]
    assert cache, "the replay cache is passed but never restored"
    key = str(cache[0]["with"]["key"])
    assert "hashFiles('pmlab/*.py')" in key
    assert "run_id" in key, "every run must save its own entry"
    assert "hashFiles('pmlab/*.py')" in str(cache[0]["with"]["restore-keys"])


def test_the_recorder_and_settle_jobs_serialise_on_the_data_branch():
    """Both push to `data`; concurrent runs would race the rebase loop."""
    groups = set()
    for name in ("record.yml", "settle.yml"):
        doc = load(str(ROOT / ".github" / "workflows" / name))
        groups.add((doc.get("concurrency") or {}).get("group"))
    assert groups == {"data-branch"}
