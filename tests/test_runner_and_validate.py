"""The run and validate loops, and the CLI around them, over a tiny synthetic benchmark. Scoring
and the workspace are faked, so no app starts: these check what the loops record, trace, and
report, not Playwright."""

import json
from pathlib import Path
from typing import Any, cast

import pytest

from agent_eval_gate import benchmark, cli, runner, scoring, telemetry, validate
from agent_eval_gate.agents import AgentResult, Recorder, ReplayAgent, TaskInput, Usage
from agent_eval_gate.benchmark import Benchmark, Task
from agent_eval_gate.scoring import SuiteRun, TrialScore
from agent_eval_gate.workspace import Workspace

FEATURE = """Feature: Vendors

  Scenario: Create a vendor
    When a member creates a vendor
    Then the response is 201

  Scenario: Duplicate names are refused
    When a member creates a vendor with an existing name
    Then the response is 409
"""
BENCHMARK = """name: tiny
version: "1"
target:
  repo: https://example.invalid/app
  ref: abc123
  app: {cwd: ".", command: "true", health: "http://127.0.0.1:{port}/"}
  tests: {cwd: ".", generated_dir: tests/generated, typecheck: "true", run: "true"}
tag_format: "@{task_id}"
"""
TASKS = """tasks:
  - id: T-1
    split: dev
    feature: features/vendors.feature
    scenario: Create a vendor
  - id: T-2
    split: heldout
    feature: features/vendors.feature
    scenario: Duplicate names are refused
"""
BUGS = """bugs:
  - {id: b1, category: status_codes, tasks: [T-1], expected_failure: 200 not 201,
     file: app.py, old: "201", new: "200"}
  - {id: b2, category: validation, tasks: [T-2], expected_failure: dup accepted,
     file: app.py, old: "409", new: "200"}
"""


class FakeWorkspace:
    def __init__(self, path: Path) -> None:
        self.path = path

    def copy_for_agent(self, dest: Path) -> Path:
        dest.mkdir(parents=True)
        return dest


class Agent:
    name = "fake"

    def __init__(self) -> None:
        self.seen: list[TaskInput] = []

    def run(self, task: TaskInput, workspace: Path, trial: int) -> AgentResult:
        self.seen.append(task)
        usage = Usage(input_tokens=100, output_tokens=20, cache_read_input_tokens=80, model="m-1")
        return AgentResult(files={f"{task.task_id}.spec.ts": "test()"}, usage=usage)


@pytest.fixture
def bench(tmp_path: Path) -> Benchmark:
    root = tmp_path / "bench"
    (root / "reference").mkdir(parents=True)
    (root / "benchmark.yaml").write_text(BENCHMARK)
    (root / "tasks.yaml").write_text(TASKS)
    (root / "bugs.yaml").write_text(BUGS)
    for task in ("T-1", "T-2"):
        (root / "reference" / f"{task}.spec.ts").write_text("test()")
    return benchmark.load(root)


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    repo = tmp_path / "repo"
    (repo / "features").mkdir(parents=True)
    (repo / "features" / "vendors.feature").write_text(FEATURE)
    (repo / "app.py").write_text("CREATED = 201\nCONFLICT = 409\n")
    return cast(Workspace, FakeWorkspace(repo))


def fake_score(passing: set[str], caught: set[str]) -> Any:
    """A scoring.score stand-in: tasks in `passing` pass and tag; bugs in `caught` are caught."""

    def score(bench: Benchmark, ws: Any, task: Task, files: dict[str, str], **_: Any) -> TrialScore:
        ok = task.id in passing
        clean = SuiteRun(passed=1, passed_tags={bench.tag(task)}) if ok else SuiteRun(failed=1)
        kills = {b.id: b.id in caught for b in bench.bugs_for(task)} if ok else {}
        return TrialScore(typechecks=True, clean=clean, tagged=ok, kills=kills)

    return score


def test_run_scores_every_trial_and_traces_usage_with_cache_tokens(
    bench: Benchmark, workspace: Workspace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scoring, "score", fake_score({"T-1"}, {"b1"}))
    trace = tmp_path / "trace.jsonl"
    agent = Agent()

    result = runner.run(
        bench,
        workspace,
        agent,
        split="all",
        trials=2,
        mode="live",
        tracer=telemetry.configure(trace),
        recorder=Recorder(tmp_path / "rec", agent.name),
    )

    assert [(t.task_id, t.trial, t.success) for t in result.trials] == [
        ("T-1", 0, True),
        ("T-1", 1, True),
        ("T-2", 0, False),
        ("T-2", 1, False),
    ]
    assert agent.seen[0].required_tag == "@T-1"
    assert "Then the response is 201" in agent.seen[0].story
    assert result.meta.model == "m-1" and result.meta.target_ref == "abc123"
    assert result.summary.task_success.successes == 2
    assert result.summary.bug_detection.successes == 2  # b1 twice; b2 never ran clean

    spans = telemetry.read_spans(trace)
    names = {s["name"] for s in spans}
    assert {"aeg.run", "aeg.trial", "aeg.agent", "aeg.score"} <= names
    agent_span = next(s for s in spans if s["name"] == "aeg.agent")
    attributes: dict[str, Any] = agent_span["attributes"]  # type: ignore[assignment]
    assert attributes["gen_ai.usage.input_tokens"] == 100
    assert attributes["aeg.usage.cache_read_input_tokens"] == 80


def test_recorded_runs_replay_to_the_same_result(
    bench: Benchmark, workspace: Workspace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scoring, "score", fake_score({"T-1", "T-2"}, {"b1"}))
    recorder = Recorder(tmp_path / "rec", "fake")
    tracer = telemetry.configure(None)
    live = runner.run(
        bench,
        workspace,
        Agent(),
        split="dev",
        trials=1,
        mode="live",
        tracer=tracer,
        recorder=recorder,
    )
    replayed = runner.run(
        bench,
        workspace,
        ReplayAgent(recorder, "fake"),
        split="dev",
        trials=1,
        mode="replay",
        tracer=tracer,
    )
    assert [t.model_dump() for t in replayed.trials] == [t.model_dump() for t in live.trials]


def test_an_agent_crash_is_a_scored_failure(
    bench: Benchmark, workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scoring, "score", fake_score(set(), set()))

    class Crashing(Agent):
        def run(self, task: TaskInput, workspace: Path, trial: int) -> AgentResult:
            raise RuntimeError("boom")

    result = runner.run(
        bench,
        workspace,
        Crashing(),
        split="dev",
        trials=1,
        mode="live",
        tracer=telemetry.configure(None),
    )
    assert result.trials[0].agent_error == "RuntimeError: boom"
    assert not result.trials[0].success


def test_validate_passes_a_sound_benchmark(
    bench: Benchmark, workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scoring, "score", fake_score({"T-1", "T-2"}, {"b1", "b2"}))
    report = validate.validate(bench, workspace)
    assert report.ok, report.problems
    assert (report.checked_tasks, report.checked_bugs) == (2, 2)


def test_validate_names_every_kind_of_problem(
    bench: Benchmark, workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    # T-2's reference fails on clean code; b1 isn't caught; one bug's text no longer applies.
    monkeypatch.setattr(scoring, "score", fake_score({"T-1"}, set()))
    (workspace.path / "app.py").write_text("CREATED = 201\nCREATED_AGAIN = 201\n")
    problems = validate.validate(bench, workspace).problems
    assert "bug b1: `old` matches 2 times in app.py" in problems
    assert "bug b2: `old` matches 0 times in app.py" in problems
    assert "bug b1: not caught by the reference test for T-1" in problems
    assert any(p.startswith("task T-2: reference fails on clean code") for p in problems)


def _write_result(path: Path, successes: list[bool]) -> None:
    from agent_eval_gate.results import RunMeta, RunResult, TrialRecord, summarize

    trials = [
        TrialRecord(
            task_id=f"T{i}",
            trial=0,
            agent_error=None,
            typechecks=True,
            clean_passed=1,
            clean_failed=0,
            load_errors=[],
            tagged=ok,
            success=ok,
            kills={},
            bugs=[],
            usage=Usage(),
            duration_s=1.0,
        )
        for i, ok in enumerate(successes)
    ]
    meta = RunMeta(
        benchmark="tiny@v1",
        target_ref="abc123",
        agent="a",
        mode="live",
        split="dev",
        trials=1,
        harness_version="0",
        started_at="now",
    )
    result = RunResult(meta=meta, trials=trials, summary=summarize(trials, {}))
    path.write_text(result.model_dump_json())


def test_cli_gate_report_split_and_power(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    base, worse = tmp_path / "base.json", tmp_path / "worse.json"
    _write_result(base, [True] * 20)
    _write_result(worse, [i >= 8 for i in range(20)])

    assert cli.main(["gate", "--baseline", str(base), "--current", str(base)]) == 0
    assert cli.main(["gate", "--baseline", str(base), "--current", str(worse)]) == 1
    assert "Gate failed." in capsys.readouterr().out
    assert cli.main(["gate", "--baseline", str(base), "--current", str(tmp_path / "no.json")]) == 2
    assert cli.main(["report", str(base)]) == 0
    assert "100% (20/20)" in capsys.readouterr().out

    repo_benchmarks = Path(__file__).parents[1] / "benchmarks"
    ui = str(repo_benchmarks / "vendor-intake-ui" / "v1")
    assert cli.main(["split", "--benchmark", ui, "--seed", "20261101", "--sampled", "dev"]) == 0
    assert cli.main(["split", "--benchmark", ui, "--seed", "1", "--sampled", "dev"]) == 1

    assert cli.main(["power", "--trials", "1", "--drops", "0", "--sims", "20"]) == 0
    assert "| 0 (false alarms) |" in capsys.readouterr().out


def test_cli_refuses_to_compare_runs_on_different_benchmarks(tmp_path: Path) -> None:
    base, other = tmp_path / "base.json", tmp_path / "other.json"
    _write_result(base, [True])
    _write_result(other, [True])
    data = json.loads(other.read_text())
    data["meta"]["benchmark"] = "tiny@v2"
    other.write_text(json.dumps(data))
    assert cli.main(["gate", "--baseline", str(base), "--current", str(other)]) == 2
