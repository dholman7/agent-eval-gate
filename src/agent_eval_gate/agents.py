"""Agents under evaluation, plus deterministic baselines and record/replay.

Any agent can be plugged in as a shell command (`CommandAgent`). It receives:
  AEG_TASK       path to a JSON file (TaskInput)
  AEG_WORKSPACE  a private copy of the target repo it may read and modify
  AEG_OUTPUT     directory to write test files into; only *.ts files there are scored
and may write AEG_OUTPUT/usage.json: {"input_tokens", "output_tokens", "cost_usd", "model"}.
"""

import json
import os
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from agent_eval_gate.benchmark import Benchmark


class TaskInput(BaseModel):
    task_id: str
    story: str
    required_tag: str
    # Where tests are expected to live, relative to the repo root.
    test_dir: str


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    model: str | None = None


class AgentResult(BaseModel):
    files: dict[str, str] = Field(default_factory=dict)
    usage: Usage = Field(default_factory=Usage)
    duration_s: float = 0.0
    error: str | None = None
    # Tail of the agent's stderr on every run, success included: its own account of what it did.
    log: str | None = None


class Agent(Protocol):
    name: str

    def run(self, task: TaskInput, workspace: Path, trial: int) -> AgentResult: ...


class CommandAgent:
    def __init__(self, name: str, command: str, timeout_s: float = 900) -> None:
        self.name = name
        self.command = command
        self.timeout_s = timeout_s

    def run(self, task: TaskInput, workspace: Path, trial: int) -> AgentResult:
        output = workspace.parent / "aeg-output"
        output.mkdir(exist_ok=True)
        task_file = workspace.parent / "aeg-task.json"
        task_file.write_text(task.model_dump_json(indent=2))
        # The harness's own virtualenv would leak into the agent and the app it starts.
        inherited = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        env = {
            **inherited,
            "AEG_TASK": str(task_file),
            "AEG_WORKSPACE": str(workspace),
            "AEG_OUTPUT": str(output),
            "AEG_TRIAL": str(trial),
        }
        started = time.monotonic()
        log: str | None = None
        try:
            completed = subprocess.run(
                self.command,
                shell=True,
                env=env,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
            )
            log = completed.stderr[-2000:] or None
            error = None if completed.returncode == 0 else log or "nonzero exit"
        except subprocess.TimeoutExpired:
            error = f"timed out after {self.timeout_s}s"
        usage_file = output / "usage.json"
        return AgentResult(
            files={p.name: p.read_text() for p in sorted(output.glob("*.ts"))},
            usage=Usage.model_validate_json(usage_file.read_text())
            if usage_file.exists()
            else Usage(),
            duration_s=time.monotonic() - started,
            error=error,
            log=log,
        )


class ReferenceAgent:
    """Returns the benchmark's own reference test. An oracle: should score at or near 100%."""

    name = "reference"

    def __init__(self, bench: "Benchmark") -> None:
        self.bench = bench

    def run(self, task: TaskInput, workspace: Path, trial: int) -> AgentResult:
        return AgentResult(files=self.bench.reference_files(self.bench.task(task.task_id)))


class ExistingTestsAgent:
    """Baseline: the target repo's current API tests, unchanged. What would be caught today."""

    name = "existing-tests"

    def __init__(self, existing_glob: str = "e2e/api/*.spec.ts") -> None:
        self.existing_glob = existing_glob

    def run(self, task: TaskInput, workspace: Path, trial: int) -> AgentResult:
        files = {p.name: p.read_text() for p in sorted(workspace.glob(self.existing_glob))}
        # Imports are relative to the original location, one directory up.
        return AgentResult(
            files={n: c.replace('from "../', 'from "../../') for n, c in files.items()}
        )


class Recorder:
    """Stores live results so CI can replay them without calling a model."""

    def __init__(self, root: Path, agent_name: str) -> None:
        self.root = root / agent_name

    def _dir(self, task_id: str, trial: int) -> Path:
        return self.root / task_id / f"trial-{trial}"

    def save(self, task_id: str, trial: int, result: AgentResult) -> None:
        directory = self._dir(task_id, trial)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "result.json").write_text(result.model_dump_json(indent=2) + "\n")

    def load(self, task_id: str, trial: int) -> AgentResult:
        path = self._dir(task_id, trial) / "result.json"
        if not path.exists():
            raise FileNotFoundError(f"no recording for {task_id} trial {trial} at {path}")
        return AgentResult.model_validate(json.loads(path.read_text()))


class ReplayAgent:
    def __init__(self, recorder: Recorder, name: str) -> None:
        self.recorder = recorder
        self.name = name

    def run(self, task: TaskInput, workspace: Path, trial: int) -> AgentResult:
        return self.recorder.load(task.task_id, trial)
