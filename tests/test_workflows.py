"""The four workflows, checked as data rather than read by eye.

Two of them push, and only to the orphan ``data`` branch: record.yml
appends snapshots and settle.yml appends settlements. None of them may
write to ``main``: the cron runs from ``main``, so a workflow that pushed
there would rewrite the branch it is launched from, and the code and the
snapshots committed on ``main`` change only by pull request. ci.yml and
analysis.yml push nothing; a failure log or a regenerated ``results/``
leaves the run as an artifact.

The other thing pinned here is that a job with nothing to do exits green.
Both the settle job and the analysis job run before the ``data`` branch
exists, and "no data yet" is the ordinary state of a fresh branch, not a
failure -- a red build for it trains the owner to ignore red builds.
"""
from __future__ import annotations

import glob
import re
import shlex
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted(glob.glob(str(ROOT / ".github" / "workflows" / "*.yml")))

#: The workflows that push, and so the only ones whose jobs may write.
PUSHERS = {"record.yml", "settle.yml"}

#: Every action a workflow may use. None of them pushes; an action outside
#: this set could push without a ``git push`` line for the checks to see.
ALLOWED_ACTIONS = {
    "actions/checkout",
    "actions/setup-python",
    "actions/cache",
    "actions/upload-artifact",
}

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


# ---------------------------------------------------------------------------
# pushes

#: Every ``git push`` in a run script, including ``git -C dir push``. Its
#: arguments run to the end of the shell command.
GIT_PUSH = re.compile(
    r"\bgit\s+(?:-[Cc]\s+\S+\s+|--?[\w-]+(?:=\S+)?\s+)*push\b"
    r"(?P<args>[^\n;&|)]*)")

#: Options that take the next word as their value.
PUSH_OPTIONS_WITH_VALUE = {"-o", "--push-option", "--repo", "--receive-pack",
                           "--exec"}

#: Options that push more than the refspecs named.
PUSH_EVERYTHING = {"--all", "--branches", "--mirror"}

#: The guard a push to the triggering branch needs.
EXCLUDES_MAIN = re.compile(r"github\.ref\s*!=\s*'refs/heads/main'")


def _excludes_main(cond: str) -> bool:
    return bool(EXCLUDES_MAIN.search(cond)) and "||" not in cond


def _names_main(refspec: str) -> bool:
    return any(part in ("main", "refs/heads/main")
               for part in refspec.lstrip("+").split(":"))


def _push_args(args: str) -> tuple[list[str], list[str]]:
    flags: list[str] = []
    positional: list[str] = []
    tokens = iter(shlex.split(args, comments=True))
    for tok in tokens:
        if tok.startswith("-"):
            flags.append(tok)
            if tok in PUSH_OPTIONS_WITH_VALUE:
                next(tokens, None)
        else:
            positional.append(tok)
    return flags, positional


def push_problems(doc: dict) -> tuple[dict[str, int], list[str]]:
    """Count the pushes in each job and list every one that could reach main.

    A push may name the data branch, as exactly ``HEAD:data``. Any other push
    must name exactly ``HEAD:$GITHUB_REF_NAME`` and sit under an ``if`` (on
    the step or its job) that excludes main. A push with no remote or no
    refspec, a remote held in a variable, a refspec that names main, and an
    action outside ALLOWED_ACTIONS are all rejected.
    """
    counts: dict[str, int] = {}
    problems: list[str] = []
    for job, spec in (doc.get("jobs") or {}).items():
        counts[job] = 0
        job_if = str(spec.get("if", ""))
        for step in spec.get("steps", []) or []:
            where = f"{job}:{step.get('name') or step.get('uses')!r}"
            uses = str(step.get("uses") or "")
            if uses and uses.split("@")[0] not in ALLOWED_ACTIONS:
                problems.append(f"{where}: uses {uses}, which may push")
            guarded = (_excludes_main(str(step.get("if", "")))
                       or _excludes_main(job_if))
            run = (step.get("run") or "").replace("\\\n", " ")
            for m in GIT_PUSH.finditer(run):
                counts[job] += 1
                flags, positional = _push_args(m.group("args"))
                if PUSH_EVERYTHING & set(flags):
                    problems.append(f"{where}: pushes every branch")
                    continue
                if not positional:
                    problems.append(f"{where}: bare `git push` names no "
                                    f"remote or refspec")
                    continue
                remote, refspecs = positional[0], positional[1:]
                if "$" in remote:
                    problems.append(f"{where}: remote {remote} is a variable")
                    continue
                if not refspecs:
                    problems.append(f"{where}: push names no refspec")
                    continue
                if any(_names_main(r) for r in refspecs):
                    problems.append(f"{where}: push names main")
                    continue
                if refspecs == ["HEAD:data"]:
                    continue
                if refspecs == ["HEAD:$GITHUB_REF_NAME"] and guarded:
                    continue
                problems.append(f"{where}: pushes {' '.join(refspecs)} "
                                f"without excluding main")
    return counts, problems


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: Path(p).name)
def test_no_step_can_push_to_main(path):
    counts, problems = push_problems(load(path))
    assert not problems, problems
    pushes = sum(counts.values())
    if Path(path).name in PUSHERS:
        assert pushes, f"{path} was expected to push to the data branch"
    else:
        assert not pushes, f"{path} was expected to push nothing"


def _workflow(*step_yaml: str, job_if: str = "") -> dict:
    job = {"runs-on": "ubuntu-latest",
           "steps": [yaml.safe_load(textwrap.dedent(s)) for s in step_yaml]}
    if job_if:
        job["if"] = job_if
    return {"jobs": {"j": job}}


#: Workflows that can push to main, each with the reason the check must give.
PUSHES_TO_MAIN = {
    "inverted guard": (_workflow("""
        name: push results
        if: github.ref == 'refs/heads/main'
        run: git push origin "HEAD:$GITHUB_REF_NAME"
        """), "without excluding main"),
    "bare git push": (_workflow("""
        name: push snapshot
        run: git push origin HEAD:data
        """, """
        name: push results
        run: |
          git commit -m results
          git push
        """), "names no remote"),
    "remote in a variable": (_workflow("""
        name: push
        run: git push "$REMOTE" HEAD:main
        """), "is a variable"),
    "data and main in one step": (_workflow("""
        name: push
        run: |
          git push origin HEAD:data
          git push origin HEAD:main
        """), "names main"),
    "guard with main named": (_workflow("""
        name: push
        if: failure() && github.ref != 'refs/heads/main'
        run: git push origin HEAD:main
        """), "names main"),
}

#: The pushes the check must still accept.
ALLOWED_PUSHES = {
    "data branch in a retry loop": _workflow("""
        name: push
        run: |
          cd archive
          for i in 1 2 3; do
            if git push origin HEAD:data; then exit 0; fi
          done
        """),
    "own branch, step guard": _workflow("""
        name: push
        if: github.ref != 'refs/heads/main'
        run: git push origin "HEAD:$GITHUB_REF_NAME"
        """),
    "own branch, job guard": _workflow("""
        name: push
        run: git -C archive push origin "HEAD:$GITHUB_REF_NAME"
        """, job_if="${{ github.ref != 'refs/heads/main' }}"),
}


@pytest.mark.parametrize("name", sorted(PUSHES_TO_MAIN))
def test_the_push_check_rejects_a_push_to_main(name):
    doc, reason = PUSHES_TO_MAIN[name]
    _, problems = push_problems(doc)
    assert any(reason in p for p in problems), problems


@pytest.mark.parametrize("name", sorted(ALLOWED_PUSHES))
def test_the_push_check_accepts_the_allowed_pushes(name):
    counts, problems = push_problems(ALLOWED_PUSHES[name])
    assert counts["j"] == 1
    assert not problems, problems


def test_the_push_check_rejects_an_action_that_could_push():
    doc = _workflow("""
        uses: stefanzweifel/git-auto-commit-action@v5
        """)
    _, problems = push_problems(doc)
    assert any("may push" in p for p in problems), problems


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


# ---------------------------------------------------------------------------
# what leaves a run

@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: Path(p).name)
def test_a_failure_log_leaves_the_run_as_an_artifact(path):
    """Every job tees its output into ci.log. On failure the log is uploaded
    with the run; it is never committed to a branch."""
    doc = load(path)
    for job, spec in doc["jobs"].items():
        runs = [s.get("run") or "" for s in spec["steps"]]
        assert not any(".ci/" in r for r in runs), f"{path}:{job}"
        if not any("ci.log" in r for r in runs):
            continue
        uploads = [s for s in spec["steps"]
                   if str(s.get("uses", "")).startswith(
                       "actions/upload-artifact@")
                   and "ci.log" in str((s.get("with") or {}).get("path"))]
        assert uploads, f"{path}:{job} writes ci.log but never uploads it"
        assert all("failure()" in str(s.get("if", "")) for s in uploads), (
            f"{path}:{job}")


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: Path(p).name)
def test_a_job_that_does_not_push_commits_nothing(path):
    doc = load(path)
    counts, _ = push_problems(doc)
    for job, step in steps(doc):
        if not counts[job]:
            assert "git commit" not in (step.get("run") or ""), (
                f"{path}:{job}:{step.get('name')!r}")


def test_the_analysis_job_keeps_its_results_as_an_artifact():
    """The replay regenerates results/ and README.md; the job uploads both,
    on success as well as on failure."""
    doc = load(str(ROOT / ".github" / "workflows" / "analysis.yml"))
    uploads = [s for _, s in steps(doc)
               if str(s.get("uses", "")).startswith("actions/upload-artifact@")
               and "results/" in str((s.get("with") or {}).get("path"))]
    assert len(uploads) == 1, uploads
    assert "README.md" in uploads[0]["with"]["path"]
    assert "failure()" not in str(uploads[0].get("if", ""))
    order = [s.get("name") for _, s in steps(doc)]
    assert order.index(uploads[0]["name"]) > order.index("replay the archive")


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
