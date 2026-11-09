import pytest

from agent_eval_gate import gate
from agent_eval_gate.agents import Usage
from agent_eval_gate.power import detection_rate
from agent_eval_gate.results import RunMeta, RunResult, Summary, TrialRecord, summarize
from agent_eval_gate.stats import Estimate, bootstrap_mean, sign_flip_p, wilson


def test_wilson_matches_a_known_value() -> None:
    # 41/50: the worked example from the plan's claim wording.
    e = wilson(41, 50)
    assert round(e.low, 3) == 0.692
    assert round(e.high, 3) == 0.902


@pytest.mark.parametrize(("k", "n"), [(0, 12), (12, 12), (1, 1)])
def test_wilson_stays_inside_zero_and_one_at_the_edges(k: int, n: int) -> None:
    e = wilson(k, n)
    assert 0.0 <= e.low <= e.value <= e.high <= 1.0
    assert e.high - e.low > 0  # never a zero-width interval from a small sample


def test_wilson_with_no_data_is_maximally_uncertain() -> None:
    assert wilson(0, 0).model_dump(include={"low", "high", "n"}) == {
        "low": 0.0,
        "high": 1.0,
        "n": 0,
    }


def test_bootstrap_is_reproducible_and_brackets_the_mean() -> None:
    values = [0.01, 0.02, 0.05, 0.03, 0.04]
    first, second = bootstrap_mean(values), bootstrap_mean(values)
    assert first == second
    assert first.low <= first.value <= first.high


def _record(
    task: str,
    *,
    success: bool,
    clean_failed: int = 0,
    kills: dict[str, bool] | None = None,
    bugs: list[str] | None = None,
) -> TrialRecord:
    return TrialRecord(
        task_id=task,
        trial=0,
        agent_error=None,
        typechecks=True,
        clean_passed=1,
        clean_failed=clean_failed,
        load_errors=[],
        tagged=success,
        success=success,
        kills=kills or {},
        bugs=bugs or [],
        usage=Usage(),
        duration_s=1.0,
    )


def test_bugs_count_as_missed_when_the_suite_failed_on_clean_code() -> None:
    trials = [
        _record("A", success=True, kills={"b1": True}, bugs=["b1"]),
        _record("B", success=False, clean_failed=1, kills={}, bugs=["b2"]),
    ]
    summary = summarize(trials, {"b1": "dates", "b2": "dates"})
    assert (summary.bug_detection.successes, summary.bug_detection.n) == (1, 2)
    assert summary.false_failure.successes == 1


def _meta(split: str = "dev", mode: str = "live") -> RunMeta:
    return RunMeta(
        benchmark="b@v1",
        target_ref="x",
        agent="a",
        mode=mode,
        split=split,
        trials=1,
        harness_version="0",
        started_at="now",
    )


def _summary_only(
    split: str, task_success: Estimate, bugs: Estimate, false_failure: Estimate
) -> RunResult:
    zero = Estimate(value=0, low=0, high=0, n=1)
    summary = Summary(
        task_success=task_success,
        pass_all_k=zero,
        bug_detection=bugs,
        false_failure=false_failure,
        cost_usd=zero,
        duration_s=zero,
    )
    return RunResult(meta=_meta(split), trials=[], summary=summary)


def _run(outcomes: dict[str, list[bool]], mode: str = "live", **trial: object) -> RunResult:
    """A run from per-task success lists; each success also kills that task's one bug."""
    records = [
        _record(task, success=ok, kills={f"{task}-bug": ok}, bugs=[f"{task}-bug"], **trial)  # type: ignore[arg-type]
        for task, oks in outcomes.items()
        for ok in oks
    ]
    return RunResult(meta=_meta(mode=mode), trials=records, summary=summarize(records, {}))


def _est(value: float, low: float, high: float) -> Estimate:
    return Estimate(value=value, low=low, high=high, n=20)


def _regressed(checks: list[gate.Check]) -> set[str]:
    return {c.metric for c in checks if c.regressed}


@pytest.mark.parametrize(
    ("diffs", "expected"),
    [
        ([-1, -1, -1], 1 / 8),  # only all-negative signs reach -3
        ([-1, -1, 1], 4 / 8),  # sums of -3 (1 pattern) and -1 (3 patterns)
        ([0, 0], 1.0),  # no change: every pattern ties the observed sum
        ([], 1.0),
        ([-2, -1], 1 / 4),  # only (-2, -1) reaches -3
    ],
)
def test_sign_flip_p_matches_hand_counts(diffs: list[int], expected: float) -> None:
    assert sign_flip_p(diffs) == pytest.approx(expected)


def test_sign_flip_p_is_the_exact_mcnemar_test_for_one_trial() -> None:
    # 5 tasks went pass -> fail, 1 went fail -> pass, 14 unchanged: binomial tail P(X <= 1 | 6, .5).
    diffs = [-1] * 5 + [1] + [0] * 14
    assert sign_flip_p(diffs) == pytest.approx(7 / 64)


def test_overlapping_intervals_pass_the_overlap_gate() -> None:
    base = _summary_only("dev", _est(0.8, 0.6, 0.9), _est(0.7, 0.5, 0.85), _est(0.1, 0.02, 0.3))
    current = _summary_only(
        "dev", _est(0.7, 0.5, 0.85), _est(0.65, 0.45, 0.8), _est(0.15, 0.05, 0.35)
    )
    assert not _regressed(gate.compare(base, current, method="overlap"))


def test_overlap_gate_fails_a_non_overlapping_drop_and_lower_is_better_for_false_failures() -> None:
    base = _summary_only("dev", _est(0.8, 0.6, 0.9), _est(0.7, 0.5, 0.85), _est(0.05, 0.0, 0.2))
    current = _summary_only("dev", _est(0.3, 0.15, 0.5), _est(0.7, 0.5, 0.85), _est(0.6, 0.4, 0.75))
    assert _regressed(gate.compare(base, current, method="overlap")) == {
        "task_success",
        "false_failure",
    }


def test_runs_on_different_splits_cannot_be_compared() -> None:
    e = _est(0.5, 0.3, 0.7)
    with pytest.raises(gate.IncomparableRuns, match="split"):
        gate.compare(_summary_only("dev", e, e, e), _summary_only("heldout", e, e, e))


def test_paired_gate_needs_per_trial_records() -> None:
    e = _est(0.5, 0.3, 0.7)
    with pytest.raises(gate.IncomparableRuns, match="per-trial"):
        gate.compare(_summary_only("dev", e, e, e), _summary_only("dev", e, e, e))


def test_paired_gate_refuses_different_task_sets() -> None:
    with pytest.raises(gate.IncomparableRuns, match="only in baseline \\['B'\\]"):
        gate.compare(_run({"A": [True], "B": [True]}), _run({"A": [True], "C": [True]}))


def test_identical_runs_pass_with_no_change() -> None:
    run = _run({t: [True, False, True] for t in "ABCDEFGHIJ"})
    checks = gate.compare(run, run)
    assert not _regressed(checks)
    assert all(c.change is not None and c.change.value == 0 for c in checks)


def test_a_drop_the_overlap_rule_misses_fails_the_paired_gate() -> None:
    # 20 tasks at 3/3; 6 drop to 2/3: 90% vs 100% of trials, intervals overlap, every move is down.
    tasks = [f"T{i:02}" for i in range(20)]
    base = _run({t: [True] * 3 for t in tasks})
    current = _run({t: [True, True, i >= 6] for i, t in enumerate(tasks)})
    assert not _regressed(gate.compare(base, current, method="overlap"))
    paired = {c.metric: c for c in gate.compare(base, current)}
    assert paired["task_success"].regressed
    assert paired["task_success"].p_value == pytest.approx(1 / 64)


def test_min_effect_keeps_a_significant_but_small_drop_from_failing() -> None:
    # 3 of 20 tasks drop pass -> fail: p = 1/8, mean drop 15 points.
    tasks = [f"T{i:02}" for i in range(20)]
    base = _run({t: [True] for t in tasks})
    current = _run({t: [i >= 3] for i, t in enumerate(tasks)})
    assert "task_success" not in _regressed(gate.compare(base, current, alpha=0.2, min_effect=0.2))
    assert "task_success" in _regressed(gate.compare(base, current, alpha=0.2, min_effect=0.15))


def test_runs_with_different_trial_counts_pair_by_task_rate() -> None:
    tasks = [f"T{i:02}" for i in range(8)]
    base = _run({t: [True] for t in tasks})
    current = _run({t: [False, False, True] for t in tasks})
    check = next(c for c in gate.compare(base, current) if c.metric == "task_success")
    assert check.change is not None and check.change.value == pytest.approx(-2 / 3)
    assert check.p_value == pytest.approx(1 / 2**8)
    assert check.regressed


def test_deterministic_runs_fail_on_any_task_that_got_worse() -> None:
    tasks = [f"T{i:02}" for i in range(20)]
    base = _run({t: [True] for t in tasks}, mode="deterministic")
    current = _run({t: [t != "T07"] for t in tasks}, mode="deterministic")
    checks = gate.compare(base, current)
    assert _regressed(checks) == {"task_success", "bug_detection"}
    assert all(c.p_value is None for c in checks)


def test_more_false_failures_is_the_bad_direction() -> None:
    tasks = [f"T{i:02}" for i in range(10)]
    base = _run({t: [True] for t in tasks})
    current = _run({t: [True] for t in tasks}, clean_failed=1)
    assert "false_failure" in _regressed(gate.compare(base, current))
    assert "false_failure" not in _regressed(gate.compare(current, base))


def test_power_simulation_is_reproducible_and_separates_noise_from_a_real_drop() -> None:
    noise = detection_rate(20, 3, 0.9, 0.0, "paired", sims=200)
    assert noise == detection_rate(20, 3, 0.9, 0.0, "paired", sims=200)
    assert noise <= 0.05
    assert detection_rate(20, 3, 0.9, 0.3, "paired", sims=200) >= 0.95
