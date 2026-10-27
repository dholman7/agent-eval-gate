"""Result records, summary metrics, and the Markdown report."""

from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, Field

from agent_eval_gate.agents import Usage
from agent_eval_gate.stats import Estimate, bootstrap_mean, wilson


class TrialRecord(BaseModel):
    task_id: str
    trial: int
    agent_error: str | None
    typechecks: bool
    clean_passed: int
    clean_failed: int
    load_errors: list[str]
    # Why tests failed on correct code; the first stop when reading a bad run.
    clean_failures: list[str] = Field(default_factory=list)
    tagged: bool
    success: bool
    kills: dict[str, bool]
    # Bugs the trial was scored against, including those skipped because the clean run failed.
    bugs: list[str]
    usage: Usage
    duration_s: float


class RunMeta(BaseModel):
    benchmark: str
    target_ref: str
    agent: str
    mode: Literal["live", "replay", "deterministic"]
    split: str
    trials: int
    harness_version: str
    started_at: str
    model: str | None = None


class Summary(BaseModel):
    task_success: Estimate
    pass_all_k: Estimate
    bug_detection: Estimate
    false_failure: Estimate
    cost_usd: Estimate
    duration_s: Estimate
    by_category: dict[str, Estimate] = Field(default_factory=dict)


class RunResult(BaseModel):
    meta: RunMeta
    trials: list[TrialRecord]
    summary: Summary


def summarize(trials: list[TrialRecord], bug_categories: dict[str, str]) -> Summary:
    by_task: dict[str, list[TrialRecord]] = defaultdict(list)
    for t in trials:
        by_task[t.task_id].append(t)
    # A bug counts as missed when the suite never got past the clean run.
    pairs = [(bug, t.kills.get(bug, False)) for t in trials for bug in t.bugs]
    category_pairs: dict[str, list[bool]] = defaultdict(list)
    for bug, caught in pairs:
        category_pairs[bug_categories.get(bug, "other")].append(caught)
    ran = [t for t in trials if not t.load_errors and t.clean_passed + t.clean_failed > 0]
    return Summary(
        task_success=wilson(sum(t.success for t in trials), len(trials)),
        pass_all_k=wilson(sum(all(t.success for t in ts) for ts in by_task.values()), len(by_task)),
        bug_detection=wilson(sum(c for _, c in pairs), len(pairs)),
        false_failure=wilson(sum(t.clean_failed > 0 for t in ran), len(ran)),
        cost_usd=bootstrap_mean([t.usage.cost_usd for t in trials]),
        duration_s=bootstrap_mean([t.duration_s for t in trials]),
        by_category={c: wilson(sum(v), len(v)) for c, v in sorted(category_pairs.items())},
    )


def _pct(e: Estimate) -> str:
    counts = f" ({e.successes}/{e.n})" if e.successes is not None else ""
    return f"{e.value:.0%}{counts}, 95% CI {e.low:.0%}–{e.high:.0%}"


def markdown(result: RunResult) -> str:
    m, s = result.meta, result.summary
    trials = f"{m.trials} trial{'s' if m.trials != 1 else ''}"
    cost = s.cost_usd
    lines = [
        f"### {m.agent} on {m.benchmark} ({m.split}, {trials})",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Task success | {_pct(s.task_success)} |",
        f"| All {m.trials} trials succeed (pass^k) | {_pct(s.pass_all_k)} |",
        f"| Seeded bugs caught | {_pct(s.bug_detection)} |",
        f"| Suites failing on correct code | {_pct(s.false_failure)} |",
        f"| Cost per trial | ${cost.value:.4f} (95% CI ${cost.low:.4f}–${cost.high:.4f}) |",
        f"| Agent time per trial | {s.duration_s.value:.1f}s |",
        "",
        "| Bug category | Caught |",
        "|---|---|",
        *[f"| {c} | {_pct(e)} |" for c, e in s.by_category.items()],
        "",
        f"Target `{m.target_ref[:12]}`, mode `{m.mode}`"
        + (f", model `{m.model}`" if m.model else "")
        + f", harness {m.harness_version}.",
    ]
    return "\n".join(lines) + "\n"
