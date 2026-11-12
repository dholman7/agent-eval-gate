"""Mutant generation and selection, with no app: the kill matrix is supplied directly."""

from pathlib import Path

from agent_eval_gate import mutants
from agent_eval_gate.scoring import parse_report

SOURCE = """def allowed(user, vendor):
    if user.role == "admin" or vendor.owner == user.id:
        return True
    return not vendor.locked


@router.post("", status_code=201)
def create():
    if total <= limit:
        return True
"""


def _generate(tmp_path: Path) -> list[mutants.Mutant]:
    (tmp_path / "app.py").write_text(SOURCE)
    return mutants.generate(tmp_path, ["app.py"])


def test_every_operator_yields_one_mutant_per_token(tmp_path: Path) -> None:
    found = {(m.line, m.operator) for m in _generate(tmp_path)}
    assert found == {
        (2, "== -> !="),
        (2, "or -> and"),
        (3, "True -> False"),
        (4, "drop not"),
        (7, "status 201 -> 200"),
        (9, "<= -> <"),
        (10, "True -> False"),
    }


def test_each_mutant_is_an_exact_text_replacement_that_applies_once(tmp_path: Path) -> None:
    for mutant in _generate(tmp_path):
        assert SOURCE.count(mutant.old) == 1, mutant.id
        assert SOURCE.replace(mutant.old, mutant.new) != SOURCE


def test_a_repeated_line_takes_the_lines_before_it_as_context(tmp_path: Path) -> None:
    # `return True` appears twice, so each mutant of it carries its preceding line.
    flags = [m for m in _generate(tmp_path) if m.operator == "True -> False"]
    assert [m.old for m in flags] == [
        '    if user.role == "admin" or vendor.owner == user.id:\n        return True\n',
        "    if total <= limit:\n        return True\n",
    ]


def test_selection_keeps_discriminating_mutants_up_to_the_per_task_limit(tmp_path: Path) -> None:
    found = _generate(tmp_path)
    tasks = [f"T{i}" for i in range(8)]  # a quarter of 8 is 2
    ids = [m.id for m in found]
    matrix = {
        ids[0]: [],  # survived every reference: dropped
        ids[1]: tasks,  # killed by every reference, likely a crash: dropped
        ids[2]: ["T0"],
        ids[3]: ["T0", "T1"],
        ids[4]: ["T0"],
        ids[5]: ["T2", "T3", "T4"],  # over a quarter of the tasks: dropped
        ids[6]: ["T5"],
    }

    chosen = mutants.select(found, matrix, tasks, per_task=2)

    kept = {b.id for b in chosen}
    assert ids[0] not in kept and ids[1] not in kept and ids[5] not in kept
    assert ids[6] in kept
    assert sum("T0" in b.tasks for b in chosen) <= 2
    assert chosen == mutants.select(found, matrix, tasks, per_task=2)  # seeded
    assert all(b.category.startswith("mutant:") for b in chosen)


def test_failed_tags_record_which_tasks_broke() -> None:
    report = {
        "suites": [
            {
                "specs": [
                    {"title": "a", "tags": ["A-1"], "tests": [{"status": "expected"}]},
                    {
                        "title": "b",
                        "tags": ["B-2"],
                        "tests": [{"status": "unexpected", "results": [{}]}],
                    },
                ]
            }
        ]
    }
    run = parse_report(report)
    assert run.passed_tags == {"@A-1"} and run.failed_tags == {"@B-2"}
