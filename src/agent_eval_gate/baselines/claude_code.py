"""Baseline: Claude Code itself as the agent, headless, with the app running for it.

`aeg run --agent claude-code`. It answers "does a purpose-built agent beat a general coding agent
handed the same task?" Claude Code gets the scenario, the single-call baseline's rules, the
benchmark's own run and type-check commands, and the app on a free port. It may read and edit
the workspace and run those two commands; every other tool and command is denied.

It runs on the Claude login (`claude -p`, with the API key stripped) in `--safe-mode`: no
CLAUDE.md, settings, plugins, hooks, MCP servers, or skills. Costs are Claude Code's list-price
estimates. Model and
effort follow AEG_PROFILE, AEG_MODEL, and AEG_EFFORT, as for the single-call baseline.
"""

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent_eval_gate.agents import AgentResult, TaskInput, Usage
from agent_eval_gate.app import running_services
from agent_eval_gate.baselines.single_call import ADDED_ENV, EFFORT, MODEL, STRIPPED_ENV

if TYPE_CHECKING:
    from agent_eval_gate.benchmark import Benchmark

TIMEOUT_S = 900
# The same per-task ceiling Storywright runs under (its --budget-usd default).
MAX_BUDGET_USD = 1.00

PROMPT = """Write Playwright {kind} tests in TypeScript for the scenario below, in this repository.

- Write exactly one test file: {path} (relative to the repository root). Import test helpers
  from "../../fixtures". Change no other file.
- Every test must carry the tag {tag}, e.g. test("...", {{ tag: "{tag}" }}, async (...) => ...).
- Test the scenario's behavior {surface}. Assert status codes, error codes,
  and response fields the scenario names.
- Tests share one database and run in parallel: give anything you create a unique name.
- Never weaken an assertion to make a test pass. Test what the scenario specifies.
- The app is already running. From {cwd}/ (your working directory), run the test with
  `{run}` and type-check with `{typecheck}`. Finish once both pass.

<scenario>
{story}</scenario>"""

SURFACES = {"api": "through the HTTP API only", "ui": "through the browser"}


def _command_prefix(command: str) -> str:
    """`npx playwright test --project=api x.ts` -> `npx playwright test`: the allowed-tool rule."""
    words = command.split()
    return " ".join(words[:3]) if words[:1] == ["npx"] else words[0]


class ClaudeCodeAgent:
    name = "claude-code"

    def __init__(self, bench: "Benchmark", binary: str | None = None) -> None:
        self.bench = bench
        self.binary = binary or os.environ.get("AEG_CLAUDE", "claude")

    def command(self, workspace: Path, run: str, typecheck: str) -> list[str]:
        allowed = [
            "Read", "Glob", "Grep", "Edit", "Write",
            f"Bash({_command_prefix(run)}:*)",
            f"Bash({_command_prefix(typecheck)}:*)",
        ]  # fmt: skip
        return [
            self.binary, "-p",
            "--model", MODEL,
            "--effort", EFFORT,
            "--output-format", "json",
            "--max-budget-usd", str(MAX_BUDGET_USD),
            "--add-dir", str(workspace),
            "--allowedTools", *allowed,
            "--setting-sources", "",
            "--safe-mode",
            "--strict-mcp-config",
            "--no-session-persistence",
        ]  # fmt: skip

    def run(self, task: TaskInput, workspace: Path, trial: int) -> AgentResult:
        spec = self.bench.target.tests
        kind = spec.kind("ui" if task.kind == "ui" else "api")
        cwd = workspace / spec.cwd
        target = workspace / task.test_dir / f"{task.task_id}.spec.ts"
        relative = os.path.relpath(target, cwd)
        # The harness's reporter flag is for scoring; plain output is what a developer reads.
        run = re.sub(r"\s--reporter=\S+", "", kind.run.format(paths=relative))
        prompt = PROMPT.format(
            kind=task.kind,
            path=target.relative_to(workspace).as_posix(),
            tag=task.required_tag,
            surface=SURFACES.get(task.kind, SURFACES["api"]),
            cwd=spec.cwd,
            run=run,
            typecheck=spec.typecheck,
            story=task.story,
        )
        web = self.bench.target.web if task.kind == "ui" else None
        started = time.monotonic()
        with running_services(workspace, self.bench.target.app, web) as values:
            env = {
                **{k: v for k, v in os.environ.items() if k not in (*STRIPPED_ENV, "VIRTUAL_ENV")},
                **{k: v.format(**values) for k, v in spec.env.items()},
                **ADDED_ENV,
            }
            try:
                completed = subprocess.run(
                    self.command(workspace, run, spec.typecheck),
                    input=prompt,
                    capture_output=True,
                    text=True,
                    cwd=cwd,
                    env=env,
                    timeout=TIMEOUT_S,
                )
            except subprocess.TimeoutExpired:
                return AgentResult(
                    duration_s=time.monotonic() - started, error=f"timed out after {TIMEOUT_S}s"
                )
        return self._result(completed, target, time.monotonic() - started)

    def _result(
        self, completed: subprocess.CompletedProcess[str], target: Path, duration_s: float
    ) -> AgentResult:
        try:
            result: dict[str, Any] = json.loads(completed.stdout)
        except json.JSONDecodeError:
            detail = (completed.stderr or completed.stdout).strip()[-500:]
            return AgentResult(duration_s=duration_s, error=f"no JSON result: {detail}")
        rows = (result.get("modelUsage") or {}).values()
        cache_read = sum(u.get("cacheReadInputTokens", 0) for u in rows)
        cache_write = sum(u.get("cacheCreationInputTokens", 0) for u in rows)
        usage = Usage(
            input_tokens=sum(u.get("inputTokens", 0) for u in rows) + cache_read + cache_write,
            output_tokens=sum(u.get("outputTokens", 0) for u in rows),
            cache_read_input_tokens=cache_read,
            cache_write_input_tokens=cache_write,
            cost_usd=round(sum(u.get("costUSD", 0.0) for u in rows), 6),
            model=",".join(sorted(result.get("modelUsage") or {})) or MODEL,
        )
        error = None
        if result.get("is_error") or result.get("subtype") != "success":
            error = f"claude -p {result.get('subtype')}: {str(result.get('result', ''))[:300]}"
        elif not target.is_file():
            error = f"no file at {target.name}"
        log = f"turns: {result.get('num_turns')}; {str(result.get('result', ''))[-1500:]}"
        return AgentResult(
            files={target.name: target.read_text()} if target.is_file() else {},
            usage=usage,
            duration_s=duration_s,
            error=error,
            log=log,
        )
