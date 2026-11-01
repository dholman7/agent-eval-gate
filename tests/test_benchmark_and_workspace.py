import json
import stat
import sys
from pathlib import Path

import pytest

import agent_eval_gate.workspace as workspace_module
from agent_eval_gate import benchmark
from agent_eval_gate.agents import CommandAgent, TaskInput
from agent_eval_gate.benchmark import Bug
from agent_eval_gate.gherkin import scenario_text
from agent_eval_gate.scoring import parse_report
from agent_eval_gate.workspace import Workspace

BENCH = Path(__file__).parents[1] / "benchmarks" / "vendor-intake" / "v1"

FEATURE = """Feature: Vendors
  Some description.

  Background:
    Given I am signed in

  Scenario: First
    When I do one thing
    Then it works

  Scenario Outline: Second
    When I send <value>
    Then I get <status>

    Examples:
      | value | status |
      | a     | 200    |
"""


def test_shipped_benchmark_is_structurally_sound() -> None:
    bench = benchmark.load(BENCH)
    assert bench.structural_problems() == []
    assert len(bench.tasks_in("dev")) == 12
    assert len(bench.tasks_in("heldout")) == 20
    assert all(bench.bugs_for(t) for t in bench.tasks)


def test_scenario_text_keeps_header_background_and_examples() -> None:
    text = scenario_text(FEATURE, "Second")
    assert "Feature: Vendors" in text
    assert "Background:" in text
    assert "| a     | 200    |" in text
    assert "When I do one thing" not in text


def test_unknown_scenario_raises() -> None:
    with pytest.raises(KeyError):
        scenario_text(FEATURE, "Missing")


def test_parse_report_counts_statuses_and_restores_tag_prefix() -> None:
    report = {
        "errors": [],
        "suites": [
            {
                "specs": [
                    {"tags": ["VEN-01"], "tests": [{"status": "expected"}]},
                    {"tags": ["VEN-01"], "tests": [{"status": "unexpected"}]},
                    {"tags": [], "tests": [{"status": "skipped"}]},
                ],
                "suites": [{"specs": [{"tags": ["@AUD-01"], "tests": [{"status": "flaky"}]}]}],
            }
        ],
    }
    run = parse_report(report)
    assert (run.passed, run.failed, run.skipped) == (2, 1, 1)
    assert run.passed_tags == {"@VEN-01", "@AUD-01"}


def test_parse_report_keeps_the_first_error_lines_without_color_codes() -> None:
    message = (
        "\x1b[2mexpect(\x1b[22mreceived).toBe(expected)\n\n"
        "Expected: 201\nReceived: 422\n  at x.ts:5"
    )
    report = {
        "suites": [
            {
                "specs": [
                    {
                        "title": "creates a vendor",
                        "tags": [],
                        "tests": [
                            {"status": "unexpected", "results": [{"error": {"message": message}}]}
                        ],
                    }
                ]
            }
        ]
    }

    run = parse_report(report)

    assert run.failures == [
        "creates a vendor: expect(received).toBe(expected) | Expected: 201 | Received: 422"
    ]


def _bug(old: str) -> Bug:
    return Bug(
        id="b", category="c", tasks=["T"], expected_failure="x", file="app.py", old=old, new="NEW"
    )


def test_mutation_applies_and_restores_even_when_the_block_fails(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("keep OLD keep\n")
    workspace = Workspace(tmp_path)
    with pytest.raises(RuntimeError), workspace.mutated(_bug("OLD")):
        assert (tmp_path / "app.py").read_text() == "keep NEW keep\n"
        raise RuntimeError
    assert (tmp_path / "app.py").read_text() == "keep OLD keep\n"


def test_mutation_refuses_ambiguous_text(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("OLD OLD\n")
    with pytest.raises(ValueError, match="found 2"), Workspace(tmp_path).mutated(_bug("OLD")):
        pass


def test_test_files_cannot_escape_their_directory(tmp_path: Path) -> None:
    with (
        pytest.raises(ValueError, match="escapes"),
        Workspace(tmp_path).with_tests("e2e/gen", {"../../x.ts": ""}),
    ):
        pass
    assert not (tmp_path / "x.ts").exists()


def test_agent_copies_get_shared_dirs_cloned_with_the_same_contents(tmp_path: Path) -> None:
    (tmp_path / "base" / "e2e" / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "base" / "e2e" / "node_modules" / "pkg" / "index.js").write_text("x")

    copy = Workspace(tmp_path / "base").copy_for_agent(tmp_path / "scratch" / "repo")

    modules = copy / "e2e" / "node_modules"
    assert (modules / "pkg" / "index.js").read_text() == "x"
    # macOS (APFS) always clones, giving a real directory; Turbopack rejects symlinked ones.
    if sys.platform == "darwin":
        assert not modules.is_symlink()


def test_without_cloning_shared_dirs_are_symlinks_that_resolve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regression: a relative workspace path produced broken symlinks in agent copies.
    monkeypatch.setattr(workspace_module, "_clone", lambda source, destination: False)
    (tmp_path / "base" / "e2e" / "node_modules").mkdir(parents=True)
    (tmp_path / "base" / "e2e" / "app.ts").write_text("")
    monkeypatch.chdir(tmp_path)

    copy = Workspace(Path("base")).copy_for_agent(tmp_path / "scratch" / "repo")

    link = copy / "e2e" / "node_modules"
    assert link.is_symlink()
    assert link.resolve() == (tmp_path / "base" / "e2e" / "node_modules").resolve()
    assert link.exists()


def test_support_files_apply_additions_only_and_are_restored(tmp_path: Path) -> None:
    pages = tmp_path / "e2e" / "fixtures" / "pages.ts"
    pages.parent.mkdir(parents=True)
    pages.write_text("class A {}\n")
    files = {
        "e2e/fixtures/pages.ts": "class A {}\nclass B {}\n",
        "e2e/fixtures/index.ts": "export {}\n",
    }

    with Workspace(tmp_path).with_support(files, ["e2e/fixtures/pages.ts"]) as rejected:
        during = pages.read_text()

    assert during == "class A {}\nclass B {}\n"
    assert pages.read_text() == "class A {}\n"
    assert rejected == ["e2e/fixtures/index.ts: not a file agents may extend"]


def test_a_support_file_that_changes_existing_lines_is_rejected(tmp_path: Path) -> None:
    pages = tmp_path / "pages.ts"
    pages.write_text("class A {}\n")

    with Workspace(tmp_path).with_support({"pages.ts": "class Z {}\n"}, ["pages.ts"]) as rejected:
        during = pages.read_text()

    assert during == "class A {}\n"
    assert rejected == [
        "pages.ts: changes or removes existing lines 1-1; only additions are allowed"
    ]


def test_agent_copies_never_share_the_base_virtualenv(tmp_path: Path) -> None:
    # A shared venv let `uv run` in a copy re-point the base's editable install at the copy.
    (tmp_path / "base" / "backend" / ".venv" / "lib").mkdir(parents=True)
    (tmp_path / "base" / "backend" / "app.py").write_text("")

    copy = Workspace(tmp_path / "base").copy_for_agent(tmp_path / "scratch" / "repo")

    assert (copy / "backend" / "app.py").exists()
    assert not (copy / "backend" / ".venv").exists()
    assert not (copy / "backend" / ".venv").is_symlink()


def test_command_agent_follows_the_contract(tmp_path: Path) -> None:
    script = tmp_path / "agent.sh"
    script.write_text(
        "#!/bin/sh\n"
        'grep -q VEN-01 "$AEG_TASK"\n'
        'echo "test" > "$AEG_OUTPUT/VEN-01.spec.ts"\n'
        'echo "ignored" > "$AEG_OUTPUT/notes.md"\n'
        'echo \'{"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.001, "model": "m"}\''
        ' > "$AEG_OUTPUT/usage.json"\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    workspace = tmp_path / "scratch" / "repo"
    workspace.mkdir(parents=True)
    task = TaskInput(
        task_id="VEN-01", story="s", required_tag="@VEN-01", test_dir="e2e/api/generated"
    )

    result = CommandAgent("script", str(script)).run(task, workspace, trial=0)

    assert result.error is None
    assert list(result.files) == ["VEN-01.spec.ts"]
    assert result.usage.cost_usd == 0.001
    assert (
        json.loads((tmp_path / "scratch" / "aeg-task.json").read_text())["required_tag"]
        == "@VEN-01"
    )


def test_command_agent_hands_over_support_files_by_repo_path(tmp_path: Path) -> None:
    script = tmp_path / "agent.sh"
    script.write_text(
        "#!/bin/sh\n"
        'grep -q \'"kind": "ui"\' "$AEG_TASK"\n'
        'echo "test" > "$AEG_OUTPUT/UI-01.spec.ts"\n'
        'mkdir -p "$AEG_OUTPUT/support/e2e/fixtures"\n'
        'echo "class A {}" > "$AEG_OUTPUT/support/e2e/fixtures/pages.ts"\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    workspace = tmp_path / "scratch" / "repo"
    workspace.mkdir(parents=True)
    task = TaskInput(
        task_id="UI-01", story="s", required_tag="@UI-01", test_dir="e2e/ui/generated", kind="ui"
    )

    result = CommandAgent("script", str(script)).run(task, workspace, trial=0)

    assert result.error is None
    assert list(result.files) == ["UI-01.spec.ts"]  # the support file is not scored as a test
    assert result.support == {"e2e/fixtures/pages.ts": "class A {}\n"}


def test_ui_tasks_need_a_web_app_and_a_ui_suite(tmp_path: Path) -> None:
    root = tmp_path / "bench"
    (root / "reference").mkdir(parents=True)
    (root / "reference" / "UI-01.spec.ts").write_text("")
    (root / "benchmark.yaml").write_text(
        "name: b\nversion: '1'\ntag_format: '@{task_id}'\ntarget:\n  repo: r\n  ref: x\n"
        "  app: {cwd: ., command: c, health: h}\n"
        "  tests: {cwd: e2e, generated_dir: e2e/api/generated, typecheck: t, run: r}\n"
    )
    (root / "tasks.yaml").write_text(
        "tasks:\n  - {id: UI-01, kind: ui, split: dev, feature: f, scenario: s}\n"
    )
    (root / "bugs.yaml").write_text(
        "bugs:\n  - {id: b1, category: c, tasks: [UI-01], expected_failure: e,\n"
        "      file: f, old: o, new: n}\n"
    )

    bench = benchmark.load(root)

    assert bench.structural_problems() == [
        "task UI-01 is a UI task but no web app or UI suite is set"
    ]
    assert bench.target.tests.kind("api").generated_dir == "e2e/api/generated"
    with pytest.raises(ValueError, match="no UI tests configured"):
        bench.target.tests.kind("ui")
