"""The Claude Code baseline, against a fake `claude` binary and a stubbed app: no model calls."""

import json
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from agent_eval_gate import benchmark
from agent_eval_gate.agents import TaskInput
from agent_eval_gate.baselines import claude_code
from agent_eval_gate.benchmark import Benchmark

BENCHMARK = """name: tiny
version: "1"
target:
  repo: https://example.invalid/app
  ref: abc123
  app: {cwd: backend, command: "true", health: "http://127.0.0.1:{port}/"}
  tests:
    cwd: e2e
    generated_dir: e2e/api/generated
    typecheck: npx tsc --noEmit
    run: npx playwright test --project=api {paths} --reporter=json
    env: {API_URL: "http://127.0.0.1:{port}", E2E_EXTERNAL_SERVERS: "1"}
tag_format: "@{task_id}"
"""
TASK = TaskInput(
    task_id="LIF-01",
    story="Scenario: A re-uploaded document is the one that gets reviewed\n",
    required_tag="@LIF-01",
    test_dir="e2e/api/generated",
)

# Records what it was given, writes FAKE_WRITE to the task's test file, prints FAKE_RESULT.
FAKE = """#!{python}
import json, os, sys
from pathlib import Path

record = {{"argv": sys.argv[1:], "stdin": sys.stdin.read(), "cwd": os.getcwd(),
          "api_url": os.environ.get("API_URL"), "external": os.environ.get("E2E_EXTERNAL_SERVERS"),
          "saw_api_key": "ANTHROPIC_API_KEY" in os.environ,
          "nonessential": os.environ.get("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC")}}
Path(os.environ["FAKE_RECORD"]).write_text(json.dumps(record))
if os.environ.get("FAKE_WRITE"):
    Path("api/generated/LIF-01.spec.ts").write_text(os.environ["FAKE_WRITE"])
print(os.environ["FAKE_RESULT"])
"""
RESULT = {
    "subtype": "success",
    "is_error": False,
    "num_turns": 9,
    "result": "Done; the test passes.",
    "modelUsage": {
        "claude-haiku-5-5": {
            "inputTokens": 500,
            "outputTokens": 400,
            "cacheCreationInputTokens": 3000,
            "cacheReadInputTokens": 20000,
            "costUSD": 0.0123,
        }
    },
}


@pytest.fixture
def bench(tmp_path: Path) -> Benchmark:
    root = tmp_path / "bench"
    root.mkdir()
    (root / "benchmark.yaml").write_text(BENCHMARK)
    (root / "tasks.yaml").write_text("tasks: []\n")
    (root / "bugs.yaml").write_text("bugs: []\n")
    return benchmark.load(root)


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, str]:
    workspace = tmp_path / "repo"
    (workspace / "e2e" / "api" / "generated").mkdir(parents=True)
    binary = tmp_path / "claude"
    binary.write_text(FAKE.format(python=sys.executable))
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    record = tmp_path / "record.json"
    monkeypatch.setenv("FAKE_RECORD", str(record))
    monkeypatch.setenv("FAKE_RESULT", json.dumps(RESULT))

    @contextmanager
    def services(*args: Any) -> Iterator[dict[str, str]]:
        yield {"port": "4321", "web_port": ""}

    monkeypatch.setattr(claude_code, "running_services", services)
    return workspace, record, str(binary)


def test_claude_code_gets_the_task_the_app_and_only_the_benchmarks_commands(
    bench: Benchmark, setup: tuple[Path, Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, record_file, binary = setup
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-be-seen")
    monkeypatch.setenv("FAKE_WRITE", "test('x', { tag: '@LIF-01' }, async () => {});")

    result = claude_code.ClaudeCodeAgent(bench, binary).run(TASK, workspace, 0)

    record = json.loads(record_file.read_text())
    argv = record["argv"]
    allowed = argv[argv.index("--allowedTools") + 1 : argv.index("--setting-sources")]
    assert result.error is None
    assert result.files == {"LIF-01.spec.ts": "test('x', { tag: '@LIF-01' }, async () => {});"}
    assert not record["saw_api_key"]  # with a key, Claude Code would bill it
    assert (record["api_url"], record["external"]) == ("http://127.0.0.1:4321", "1")
    assert Path(record["cwd"]).resolve() == (workspace / "e2e").resolve()
    assert allowed == [
        "Read", "Glob", "Grep", "Edit", "Write",
        "Bash(npx playwright test:*)",
        "Bash(npx tsc --noEmit:*)",
    ]  # fmt: skip
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert {"--safe-mode", "--strict-mcp-config"} <= set(argv)
    assert record["nonessential"] == "1"  # no uncached side request repeating the prompt
    prompt = record["stdin"]
    assert "e2e/api/generated/LIF-01.spec.ts" in prompt and "@LIF-01" in prompt
    assert "`npx playwright test --project=api api/generated/LIF-01.spec.ts`" in prompt
    assert "--reporter" not in prompt
    assert "A re-uploaded document" in prompt
    assert result.usage.input_tokens == 23500  # all input, cached or not
    assert result.usage.cache_read_input_tokens == 20000
    assert result.usage.cost_usd == pytest.approx(0.0123)
    assert result.usage.model == "claude-haiku-5-5"


def test_no_test_file_is_a_scored_error(bench: Benchmark, setup: tuple[Path, Path, str]) -> None:
    workspace, _, binary = setup

    result = claude_code.ClaudeCodeAgent(bench, binary).run(TASK, workspace, 0)

    assert result.files == {}
    assert result.error == "no file at LIF-01.spec.ts"
    assert result.usage.cost_usd == pytest.approx(0.0123)  # spend is kept on failure


def test_a_failed_session_is_an_error_and_its_file_is_still_scored(
    bench: Benchmark, setup: tuple[Path, Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, _, binary = setup
    monkeypatch.setenv("FAKE_WRITE", "partial")
    monkeypatch.setenv(
        "FAKE_RESULT", json.dumps({**RESULT, "subtype": "error_max_budget_usd", "is_error": True})
    )

    result = claude_code.ClaudeCodeAgent(bench, binary).run(TASK, workspace, 0)

    assert result.error is not None and result.error.startswith("claude -p error_max_budget_usd")
    # As for any agent that exits with an error, what it left is scored.
    assert result.files == {"LIF-01.spec.ts": "partial"}
