"""Seeded bugs chosen by code, not by hand: mutation operators and a kill matrix.

Hand-written bugs are only as varied as their author, who also wrote the tasks and the agent.
Here, standard mutation operators are applied at every eligible token of the target's backend
source. Each mutant is run against every task's reference test, and the kill matrix records
which tasks' tests catch it. A mutant counts when at least one task's reference catches it but
no more than a quarter of them: one that every test catches usually just crashes the app, and
one nobody catches is often equivalent to the original. Up to `per_task` are drawn for each task
with a fixed seed, in code, so the selection is reproducible and nobody picks them.
"""

import io
import random
import tokenize
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from agent_eval_gate.app import AppStartError, running_services
from agent_eval_gate.benchmark import Benchmark, Bug
from agent_eval_gate.scoring import run_suite
from agent_eval_gate.workspace import Workspace

# Token -> replacement. Operators that change a comparison, a boolean, or a returned flag.
SWAPS = {
    "<": "<=",
    "<=": "<",
    ">": ">=",
    ">=": ">",
    "==": "!=",
    "!=": "==",
    "and": "or",
    "or": "and",
    "True": "False",
    "False": "True",
}
# HTTP status codes -> a plausible wrong one.
STATUS = {
    "200": "201",
    "201": "200",
    "204": "200",
    "400": "422",
    "401": "403",
    "403": "401",
    "404": "403",
    "409": "400",
    "413": "400",
    "415": "400",
    "422": "400",
}
SEED = 20261111


@dataclass(frozen=True)
class Mutant:
    id: str
    file: str
    line: int
    operator: str
    old: str
    new: str

    def bug(self, tasks: list[str]) -> Bug:
        return Bug(
            id=self.id,
            category=f"mutant:{self.operator}",
            tasks=tasks,
            expected_failure=f"{self.operator} at {self.file}:{self.line}",
            file=self.file,
            old=self.old,
            new=self.new,
        )


def _replacements(source: str) -> Iterator[tuple[int, int, str, str, str]]:
    """(line, column, operator name, old token, new token) for every eligible token."""
    tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    for i, tok in enumerate(tokens):
        line, col = tok.start
        if tok.type in (tokenize.OP, tokenize.NAME) and tok.string in SWAPS:
            yield line, col, f"{tok.string} -> {SWAPS[tok.string]}", tok.string, SWAPS[tok.string]
        elif tok.type == tokenize.NAME and tok.string == "not":
            following = tokens[i + 1] if i + 1 < len(tokens) else None
            # `not x` -> `x`; `is not` and `not in` change meaning in ways the swaps already cover.
            previous = tokens[i - 1].string if i else ""
            if following is not None and following.string != "in" and previous != "is":
                yield line, col, "drop not", "not ", ""
        elif tok.type == tokenize.NUMBER and tok.string in STATUS:
            yield (
                line,
                col,
                f"status {tok.string} -> {STATUS[tok.string]}",
                tok.string,
                STATUS[tok.string],
            )


def _unique_context(lines: list[str], index: int) -> tuple[int, int]:
    """The smallest run of lines ending at `index` whose text occurs exactly once in the file."""
    text = "".join(lines)
    start = index
    while start > 0 and text.count("".join(lines[start : index + 1])) != 1:
        start -= 1
    return start, index + 1


def generate(repo: Path, paths: list[str]) -> list[Mutant]:
    """Every single-token mutant in the given files (relative to `repo`)."""
    mutants = []
    for relative in paths:
        source = (repo / relative).read_text()
        lines = source.splitlines(keepends=True)
        for line, col, operator, old_token, new_token in _replacements(source):
            row = lines[line - 1]
            if row[col : col + len(old_token)] != old_token:
                continue  # a token spanning lines; skip rather than guess
            mutated_row = row[:col] + new_token + row[col + len(old_token) :]
            start, end = _unique_context(lines, line - 1)
            old = "".join(lines[start:end])
            new = "".join(lines[start : line - 1]) + mutated_row + "".join(lines[line:end])
            if old == new or source.count(old) != 1:
                continue
            slug = relative.replace("/", "_").removesuffix(".py")
            mutants.append(Mutant(f"mut-{slug}-{line}-{col}", relative, line, operator, old, new))
    return mutants


def kill_matrix(
    bench: Benchmark, workspace: Workspace, mutants: list[Mutant]
) -> dict[str, list[str]]:
    """Task ids whose reference tests fail under each mutant (every task, for a crashing app)."""
    files: dict[str, str] = {}
    for task in bench.tasks:
        files.update(bench.reference_files(task))
    tag_to_task = {bench.tag(t): t.id for t in bench.tasks}
    reference_dir = str(Path(bench.target.tests.generated_dir).parent / "reference")
    matrix: dict[str, list[str]] = {}
    with workspace.with_tests(reference_dir, files) as directory:
        with running_services(workspace.path, bench.target.app, None) as values:
            clean = run_suite(bench, workspace.path, values, directory)
        if clean.failed or clean.errors:
            raise RuntimeError(
                f"references fail on clean code: {clean.failures[:3] or clean.errors[:1]}"
            )
        for mutant in mutants:
            try:
                with (
                    workspace.mutated(mutant.bug([])),
                    running_services(workspace.path, bench.target.app, None) as values,
                ):
                    run = run_suite(bench, workspace.path, values, directory)
                killed = sorted(tag_to_task[t] for t in run.failed_tags if t in tag_to_task)
                if run.errors and not killed:
                    killed = sorted(tag_to_task.values())
            except AppStartError:
                killed = sorted(tag_to_task.values())
            matrix[mutant.id] = killed
    return matrix


def select(
    mutants: list[Mutant],
    matrix: dict[str, list[str]],
    tasks: list[str],
    per_task: int = 2,
    seed: int = SEED,
) -> list[Bug]:
    """Discriminating mutants, up to `per_task` per task, drawn with a fixed seed."""
    limit = max(1, len(tasks) // 4)
    eligible = [m for m in mutants if 1 <= len(matrix.get(m.id, [])) <= limit]
    rng = random.Random(seed)  # noqa: S311 - reproducible selection, not security
    chosen: dict[str, Mutant] = {}
    for task in sorted(tasks):
        pool = [m for m in eligible if task in matrix[m.id] and m.id not in chosen]
        have = sum(task in matrix[m.id] for m in chosen.values())
        for mutant in rng.sample(pool, min(len(pool), max(0, per_task - have))):
            chosen[mutant.id] = mutant
    return [m.bug(matrix[m.id]) for m in sorted(chosen.values(), key=lambda m: m.id)]
