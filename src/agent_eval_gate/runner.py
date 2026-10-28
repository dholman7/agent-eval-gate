"""Runs an agent over a benchmark split: agent -> record -> score, one trial at a time."""

import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from opentelemetry.trace import Tracer

from agent_eval_gate import __version__, scoring
from agent_eval_gate.agents import Agent, AgentResult, Recorder, TaskInput
from agent_eval_gate.benchmark import Benchmark, Split
from agent_eval_gate.gherkin import scenario_text
from agent_eval_gate.results import RunMeta, RunResult, TrialRecord, summarize
from agent_eval_gate.workspace import Workspace

logger = logging.getLogger(__name__)


def task_input(bench: Benchmark, workspace: Workspace, task_id: str) -> TaskInput:
    task = bench.task(task_id)
    feature = (workspace.path / task.feature).read_text()
    return TaskInput(
        task_id=task.id,
        story=scenario_text(feature, task.scenario),
        required_tag=bench.tag(task),
        test_dir=bench.target.tests.generated_dir,
    )


def run(
    bench: Benchmark,
    workspace: Workspace,
    agent: Agent,
    *,
    split: Split | Literal["all"],
    trials: int,
    mode: Literal["live", "replay", "deterministic"],
    tracer: Tracer,
    recorder: Recorder | None = None,
    task_ids: list[str] | None = None,
) -> RunResult:
    tasks = [t for t in bench.tasks_in(split) if not task_ids or t.id in task_ids]
    records: list[TrialRecord] = []
    model: str | None = None
    with tracer.start_as_current_span(
        "aeg.run",
        attributes={"aeg.benchmark": bench.key, "aeg.agent": agent.name, "aeg.split": split},
    ):
        for task in tasks:
            spec = task_input(bench, workspace, task.id)
            for trial in range(trials):
                with tracer.start_as_current_span(
                    "aeg.trial", attributes={"aeg.task": task.id, "aeg.trial": trial}
                ) as span:
                    with (
                        tempfile.TemporaryDirectory(prefix="aeg-agent-") as scratch,
                        tracer.start_as_current_span("aeg.agent") as agent_span,
                    ):
                        copy = workspace.copy_for_agent(Path(scratch) / "repo")
                        try:
                            result = agent.run(spec, copy, trial)
                        except (
                            Exception
                        ) as exc:  # an agent crash is a scored failure, not a harness crash
                            logger.exception("agent %s failed on %s", agent.name, task.id)
                            result = AgentResult(error=f"{type(exc).__name__}: {exc}")
                        if result.usage.model:
                            model = result.usage.model
                            agent_span.set_attribute("gen_ai.request.model", result.usage.model)
                        agent_span.set_attribute(
                            "gen_ai.usage.input_tokens", result.usage.input_tokens
                        )
                        agent_span.set_attribute(
                            "gen_ai.usage.output_tokens", result.usage.output_tokens
                        )
                    if recorder is not None and mode == "live":
                        recorder.save(task.id, trial, result)
                    with tracer.start_as_current_span("aeg.score"):
                        scored = scoring.score(bench, workspace, task, result.files)
                    record = TrialRecord(
                        task_id=task.id,
                        trial=trial,
                        agent_error=result.error,
                        agent_log=result.log,
                        typechecks=scored.typechecks,
                        clean_passed=scored.clean.passed,
                        clean_failed=scored.clean.failed,
                        load_errors=scored.clean.errors,
                        clean_failures=scored.clean.failures[:5],
                        tagged=scored.tagged,
                        success=scored.success,
                        kills=scored.kills,
                        bugs=[b.id for b in bench.bugs_for(task)],
                        usage=result.usage,
                        duration_s=result.duration_s,
                    )
                    span.set_attribute("aeg.success", record.success)
                    span.set_attribute("aeg.bugs_caught", sum(record.kills.values()))
                    records.append(record)
                    logger.info(
                        "%s trial %d: success=%s caught=%d/%d",
                        task.id,
                        trial,
                        record.success,
                        sum(record.kills.values()),
                        len(record.bugs),
                    )
    meta = RunMeta(
        benchmark=bench.key,
        target_ref=bench.target.ref,
        agent=agent.name,
        mode=mode,
        split=split,
        trials=trials,
        harness_version=__version__,
        started_at=datetime.now(UTC).isoformat(timespec="seconds"),
        model=model,
    )
    categories = {b.id: b.category for b in bench.bugs}
    return RunResult(meta=meta, trials=records, summary=summarize(records, categories))
