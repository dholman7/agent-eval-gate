"""Proves the benchmark is sound before any agent is scored against it.

For every task: the reference test passes on clean code. For every bug: its text applies exactly
once, and the reference test of every task it lists fails under it.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from agent_eval_gate import scoring
from agent_eval_gate.benchmark import Benchmark
from agent_eval_gate.gherkin import scenario_text
from agent_eval_gate.workspace import Workspace

logger = logging.getLogger(__name__)


@dataclass
class Report:
    problems: list[str] = field(default_factory=list)
    checked_tasks: int = 0
    checked_bugs: int = 0

    @property
    def ok(self) -> bool:
        return not self.problems


def validate(bench: Benchmark, workspace: Workspace, task_ids: list[str] | None = None) -> Report:
    report = Report(problems=bench.structural_problems())
    for bug in bench.bugs:
        count = (workspace.path / bug.file).read_text().count(bug.old)
        if count != 1:
            report.problems.append(f"bug {bug.id}: `old` matches {count} times in {bug.file}")
    for task in bench.tasks:
        if task_ids and task.id not in task_ids:
            continue
        try:
            scenario_text((workspace.path / task.feature).read_text(), task.scenario)
        except (KeyError, FileNotFoundError) as exc:
            report.problems.append(f"task {task.id}: {exc}")
            continue
        reference = bench.reference_file(task)
        if not reference.is_file():
            continue
        reference_dir = str(Path(bench.target.tests.generated_dir).parent / "reference")
        result = scoring.score(
            bench, workspace, task, bench.reference_files(task), test_dir=reference_dir
        )
        report.checked_tasks += 1
        if not result.clean_pass:
            detail = result.clean.errors[:1] or [f"{result.clean.failed} failed"]
            report.problems.append(f"task {task.id}: reference fails on clean code ({detail[0]})")
            continue
        if not result.tagged:
            report.problems.append(
                f"task {task.id}: reference has no passing test tagged {bench.tag(task)}"
            )
        if not result.typechecks:
            report.problems.append(f"task {task.id}: reference does not type-check")
        for bug_id, caught in result.kills.items():
            report.checked_bugs += 1
            if not caught:
                report.problems.append(
                    f"bug {bug_id}: not caught by the reference test for {task.id}"
                )
        logger.info(
            "%s: reference ok, caught %d/%d", task.id, sum(result.kills.values()), len(result.kills)
        )
    return report
