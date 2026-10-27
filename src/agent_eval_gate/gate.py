"""Compares a run to a stored baseline and fails only on regressions larger than the noise."""

from dataclasses import dataclass

from agent_eval_gate.results import RunResult
from agent_eval_gate.stats import Estimate

# Metric name -> whether higher is better.
GATED = {"task_success": True, "bug_detection": True, "false_failure": False}


@dataclass
class Check:
    metric: str
    baseline: Estimate
    current: Estimate
    regressed: bool


class IncomparableRuns(ValueError):
    pass


def compare(baseline: RunResult, current: RunResult) -> list[Check]:
    """A regression is when the intervals don't overlap in the bad direction.

    Overlapping intervals pass: with tens of trials, a few points of movement is noise, and a
    gate that fails on noise gets disabled.
    """
    for field in ("benchmark", "split"):
        if getattr(baseline.meta, field) != getattr(current.meta, field):
            raise IncomparableRuns(
                f"{field} differs: baseline {getattr(baseline.meta, field)!r}, "
                f"current {getattr(current.meta, field)!r}"
            )
    checks = []
    for metric, higher_is_better in GATED.items():
        base: Estimate = getattr(baseline.summary, metric)
        cur: Estimate = getattr(current.summary, metric)
        regressed = cur.high < base.low if higher_is_better else cur.low > base.high
        checks.append(Check(metric, base, cur, regressed))
    return checks


def _range(e: Estimate) -> str:
    return f"{e.value:.0%} ({e.low:.0%}–{e.high:.0%})"


def markdown(checks: list[Check]) -> str:
    rows = [
        f"| {c.metric.replace('_', ' ')} | {_range(c.baseline)} | {_range(c.current)} "
        f"| {'regressed' if c.regressed else 'ok'} |"
        for c in checks
    ]
    verdict = "Gate failed." if any(c.regressed for c in checks) else "Gate passed."
    return "\n".join(
        ["| Metric | Baseline | Current | Result |", "|---|---|---|---|", *rows, "", verdict, ""]
    )
