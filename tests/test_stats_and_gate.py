import pytest

from agent_eval_gate import gate
from agent_eval_gate.agents import Usage
from agent_eval_gate.results import RunMeta, RunResult, TrialRecord, summarize
from agent_eval_gate.stats import Estimate, bootstrap_mean, wilson


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


def _result(
    split: str, task_success: Estimate, bugs: Estimate, false_failure: Estimate
) -> RunResult:
    zero = Estimate(value=0, low=0, high=0, n=1)
    meta = RunMeta(
        benchmark="b@v1",
        target_ref="x",
        agent="a",
        mode="replay",
        split=split,
        trials=1,
        harness_version="0",
        started_at="now",
    )
    from agent_eval_gate.results import Summary

    summary = Summary(
        task_success=task_success,
        pass_all_k=zero,
        bug_detection=bugs,
        false_failure=false_failure,
        cost_usd=zero,
        duration_s=zero,
    )
    return RunResult(meta=meta, trials=[], summary=summary)


def _est(value: float, low: float, high: float) -> Estimate:
    return Estimate(value=value, low=low, high=high, n=20)


def test_overlapping_intervals_pass_the_gate() -> None:
    base = _result("dev", _est(0.8, 0.6, 0.9), _est(0.7, 0.5, 0.85), _est(0.1, 0.02, 0.3))
    current = _result("dev", _est(0.7, 0.5, 0.85), _est(0.65, 0.45, 0.8), _est(0.15, 0.05, 0.35))
    assert not any(c.regressed for c in gate.compare(base, current))


def test_non_overlapping_drop_fails_and_lower_is_better_for_false_failures() -> None:
    base = _result("dev", _est(0.8, 0.6, 0.9), _est(0.7, 0.5, 0.85), _est(0.05, 0.0, 0.2))
    current = _result("dev", _est(0.3, 0.15, 0.5), _est(0.7, 0.5, 0.85), _est(0.6, 0.4, 0.75))
    regressed = {c.metric for c in gate.compare(base, current) if c.regressed}
    assert regressed == {"task_success", "false_failure"}


def test_runs_on_different_splits_cannot_be_compared() -> None:
    e = _est(0.5, 0.3, 0.7)
    with pytest.raises(gate.IncomparableRuns, match="split"):
        gate.compare(_result("dev", e, e, e), _result("heldout", e, e, e))
