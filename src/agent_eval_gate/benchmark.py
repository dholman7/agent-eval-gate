"""Benchmark definition: target repo, tasks, and seeded bugs, loaded from a version directory."""

from collections import Counter
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

Split = Literal["dev", "heldout"]


class AppSpec(BaseModel):
    cwd: str
    command: str
    env: dict[str, str] = Field(default_factory=dict)
    health: str


class SuiteSpec(BaseModel):
    cwd: str
    generated_dir: str
    typecheck: str
    run: str
    env: dict[str, str] = Field(default_factory=dict)


class Target(BaseModel):
    repo: str
    ref: str
    setup: list[str] = Field(default_factory=list)
    app: AppSpec
    tests: SuiteSpec


class Task(BaseModel):
    id: str
    split: Split
    feature: str
    scenario: str


class Bug(BaseModel):
    id: str
    category: str
    tasks: list[str]
    expected_failure: str
    file: str
    old: str
    new: str


class Benchmark(BaseModel):
    root: Path
    name: str
    version: str
    target: Target
    tag_format: str
    tasks: list[Task]
    bugs: list[Bug]

    @property
    def key(self) -> str:
        return f"{self.name}@v{self.version}"

    def tag(self, task: Task) -> str:
        return self.tag_format.format(task_id=task.id)

    def task(self, task_id: str) -> Task:
        return next(t for t in self.tasks if t.id == task_id)

    def tasks_in(self, split: Split | Literal["all"]) -> list[Task]:
        return [t for t in self.tasks if split in ("all", t.split)]

    def bugs_for(self, task: Task) -> list[Bug]:
        return [b for b in self.bugs if task.id in b.tasks]

    def reference_file(self, task: Task) -> Path:
        return self.root / "reference" / f"{task.id}.spec.ts"

    def reference_files(self, task: Task) -> dict[str, str]:
        """The task's reference spec plus shared helpers (files starting with `_`)."""
        spec = self.reference_file(task)
        support = sorted((self.root / "reference").glob("_*.ts"))
        return {spec.name: spec.read_text(), **{p.name: p.read_text() for p in support}}

    def structural_problems(self) -> list[str]:
        """Checks that need no running app: ids, splits, references, bug wiring."""
        problems = []
        for kind, ids in (("task", [t.id for t in self.tasks]), ("bug", [b.id for b in self.bugs])):
            problems += [f"duplicate {kind} id {i}" for i, n in Counter(ids).items() if n > 1]
        task_ids = {t.id for t in self.tasks}
        for bug in self.bugs:
            problems += [
                f"bug {bug.id} names unknown task {t}" for t in bug.tasks if t not in task_ids
            ]
        for task in self.tasks:
            if not self.reference_file(task).is_file():
                problems.append(f"task {task.id} has no reference test")
            if not self.bugs_for(task):
                problems.append(f"task {task.id} has no seeded bug")
        return problems


def load(root: Path) -> Benchmark:
    meta = yaml.safe_load((root / "benchmark.yaml").read_text())
    tasks = yaml.safe_load((root / "tasks.yaml").read_text())["tasks"]
    bugs = yaml.safe_load((root / "bugs.yaml").read_text())["bugs"]
    return Benchmark.model_validate({**meta, "root": root, "tasks": tasks, "bugs": bugs})
