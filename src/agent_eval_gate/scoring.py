"""Scores a set of generated test files against the clean app and each seeded bug."""

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_eval_gate.app import running_app
from agent_eval_gate.benchmark import Benchmark, Task
from agent_eval_gate.workspace import Workspace


@dataclass
class SuiteRun:
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    # Load or syntax errors: Playwright reports these instead of running tests.
    errors: list[str] = field(default_factory=list)
    passed_tags: set[str] = field(default_factory=set)
    # "<test title>: <first line of the assertion error>" for each failed test.
    failures: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.passed + self.failed


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _first_error(test: dict[str, Any]) -> str:
    results = test.get("results") or [{}]
    last = results[-1]
    error: dict[str, Any] = last.get("error") or next(iter(last.get("errors") or []), {})
    message = _ANSI.sub("", str(error.get("message", "no error message")))
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    # Playwright puts the matcher on line 1 and Expected/Received below it; keep both.
    return " | ".join(lines[:3])[:300]


@dataclass
class TrialScore:
    typechecks: bool
    clean: SuiteRun
    tagged: bool
    # Bug id -> caught. Empty when the suite didn't pass on clean code.
    kills: dict[str, bool]

    @property
    def clean_pass(self) -> bool:
        return not self.clean.errors and self.clean.total > 0 and self.clean.failed == 0

    @property
    def success(self) -> bool:
        return self.typechecks and self.clean_pass and self.tagged


def parse_report(report: dict[str, Any]) -> SuiteRun:
    """Reads Playwright's JSON reporter output."""
    run = SuiteRun(errors=[str(e.get("message", e))[:500] for e in report.get("errors", [])])

    def walk(suite: dict[str, Any]) -> None:
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                status = test.get("status")  # expected | unexpected | flaky | skipped
                if status == "skipped":
                    run.skipped += 1
                elif status in ("expected", "flaky"):
                    run.passed += 1
                    # The JSON reporter drops the leading "@" that test authors write.
                    run.passed_tags.update(f"@{t.lstrip('@')}" for t in spec.get("tags", []))
                else:
                    run.failed += 1
                    run.failures.append(f"{spec.get('title', '?')}: {_first_error(test)}")
        for child in suite.get("suites", []):
            walk(child)

    for suite in report.get("suites", []):
        walk(suite)
    return run


def _suite_env(bench: Benchmark, port: int) -> dict[str, str]:
    values = {"port": str(port)}
    return {**os.environ, **{k: v.format(**values) for k, v in bench.target.tests.env.items()}}


def run_suite(bench: Benchmark, repo: Path, port: int, test_dir: Path) -> SuiteRun:
    spec = bench.target.tests
    cwd = repo / spec.cwd
    paths = os.path.relpath(test_dir, cwd)
    result = subprocess.run(
        spec.run.format(paths=paths),
        shell=True,
        cwd=cwd,
        env=_suite_env(bench, port),
        capture_output=True,
        text=True,
    )
    try:
        # The reporter prints JSON on stdout even when tests fail.
        return parse_report(json.loads(result.stdout))
    except json.JSONDecodeError:
        return SuiteRun(errors=[(result.stderr or result.stdout)[-1000:] or "no reporter output"])


def typechecks(bench: Benchmark, repo: Path) -> bool:
    spec = bench.target.tests
    result = subprocess.run(spec.typecheck, shell=True, cwd=repo / spec.cwd, capture_output=True)
    return result.returncode == 0


def score(
    bench: Benchmark,
    workspace: Workspace,
    task: Task,
    files: dict[str, str],
    test_dir: str | None = None,
) -> TrialScore:
    """Runs `files` on clean code, then under each of the task's bugs if the clean run passed."""
    relative = test_dir or bench.target.tests.generated_dir
    with workspace.with_tests(relative, files) as directory:
        checks = typechecks(bench, workspace.path)
        with running_app(workspace.path, bench.target.app) as port:
            clean = run_suite(bench, workspace.path, port, directory)
        result = TrialScore(
            typechecks=checks, clean=clean, tagged=bench.tag(task) in clean.passed_tags, kills={}
        )
        if not result.clean_pass:
            return result
        for bug in bench.bugs_for(task):
            with workspace.mutated(bug), running_app(workspace.path, bench.target.app) as port:
                buggy = run_suite(bench, workspace.path, port, directory)
            result.kills[bug.id] = buggy.failed > 0 or bool(buggy.errors)
        return result
