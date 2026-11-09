"""`aeg` command line: validate a benchmark, run an agent, gate against a baseline."""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Literal

from agent_eval_gate import benchmark, gate, power, results, runner, telemetry, validate
from agent_eval_gate.agents import (
    Agent,
    CommandAgent,
    ExistingTestsAgent,
    Recorder,
    ReferenceAgent,
    ReplayAgent,
)
from agent_eval_gate.workspace import Workspace

BUILTIN_AGENTS = ("reference", "existing-tests")


def _write_summary(text: str) -> None:
    """Appends to the GitHub Actions job summary when running in CI, and prints either way."""
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as out:
            out.write(text + "\n")


def _workspace(args: argparse.Namespace, bench: benchmark.Benchmark) -> Workspace:
    return Workspace.prepare(bench.target, Path(args.cache_dir), source=args.target_source)


Mode = Literal["live", "replay", "deterministic"]


def _agent(args: argparse.Namespace, bench: benchmark.Benchmark) -> tuple[Agent, Mode]:
    if args.agent == "reference":
        return ReferenceAgent(bench), "deterministic"
    if args.agent == "existing-tests":
        return ExistingTestsAgent(), "deterministic"
    if args.replay:
        return ReplayAgent(Recorder(Path(args.recordings), args.agent), args.agent), "replay"
    if not args.command:
        raise SystemExit(f"agent {args.agent!r} needs --command (or --replay)")
    return CommandAgent(args.agent, args.command), "live"


def cmd_validate(args: argparse.Namespace) -> int:
    bench = benchmark.load(Path(args.benchmark))
    report = validate.validate(bench, _workspace(args, bench), task_ids=args.task or None)
    for problem in report.problems:
        print(f"  - {problem}")
    print(
        f"{bench.key}: {report.checked_tasks} references and {report.checked_bugs} bug checks run, "
        f"{len(report.problems)} problem(s)"
    )
    return 0 if report.ok else 1


def cmd_run(args: argparse.Namespace) -> int:
    bench = benchmark.load(Path(args.benchmark))
    agent, mode = _agent(args, bench)
    tracer = telemetry.configure(Path(args.trace) if args.trace else None)
    recorder = Recorder(Path(args.recordings), agent.name) if mode == "live" else None
    result = runner.run(
        bench,
        _workspace(args, bench),
        agent,
        split=args.split,
        trials=args.trials,
        mode=mode,
        tracer=tracer,
        recorder=recorder,
        task_ids=args.task or None,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result.model_dump_json(indent=2) + "\n")
    _write_summary(results.markdown(result))
    return 0


def cmd_gate(args: argparse.Namespace) -> int:
    for path in (args.baseline, args.current):
        if not Path(path).is_file():
            print(f"No result file at {path}; `aeg run --out {path}` writes one.", file=sys.stderr)
            return 2
    base = results.RunResult.model_validate_json(Path(args.baseline).read_text())
    current = results.RunResult.model_validate_json(Path(args.current).read_text())
    try:
        checks = gate.compare(base, current, args.method, args.alpha, args.min_effect)
    except gate.IncomparableRuns as exc:
        print(f"Can't compare these runs: {exc}", file=sys.stderr)
        return 2
    _write_summary(gate.markdown(checks, args.method, args.alpha, args.min_effect))
    return 1 if any(c.regressed for c in checks) else 0


def cmd_split(args: argparse.Namespace) -> int:
    bench = benchmark.load(Path(args.benchmark))
    problem = benchmark.split_problem(bench, args.seed, args.sampled)
    if problem:
        print(problem, file=sys.stderr)
        return 1
    print(f"{bench.key}: {args.sampled} split = random.Random({args.seed}).sample of the tasks")
    return 0


def cmd_power(args: argparse.Namespace) -> int:
    print(power.table(args.tasks, args.trials, args.base_rate, args.drops, args.sims), end="")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    _write_summary(
        results.markdown(results.RunResult.model_validate_json(Path(args.result).read_text()))
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aeg", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command_name", required=True)

    def target_options(p: argparse.ArgumentParser) -> None:
        p.add_argument("--benchmark", default="benchmarks/vendor-intake/v1")
        p.add_argument(
            "--cache-dir", default=".aeg-cache", help="where the target repo is checked out"
        )
        p.add_argument(
            "--target-source", help="clone from this path or URL instead of the target repo"
        )
        p.add_argument("--task", action="append", help="limit to a task id (repeatable)")

    v = sub.add_parser("validate", help="prove references pass and every bug is catchable")
    target_options(v)
    v.set_defaults(func=cmd_validate)

    r = sub.add_parser("run", help="run an agent over a benchmark split")
    target_options(r)
    r.add_argument(
        "--agent", required=True, help=f"agent name; built in: {', '.join(BUILTIN_AGENTS)}"
    )
    r.add_argument(
        "--command", help="shell command that runs the agent (see agents.py for the contract)"
    )
    r.add_argument(
        "--replay", action="store_true", help="use recorded results instead of calling the agent"
    )
    r.add_argument("--recordings", default="recordings")
    r.add_argument("--split", choices=["dev", "heldout", "all"], default="dev")
    r.add_argument("--trials", type=int, default=1)
    r.add_argument("--out", default="results/latest.json")
    r.add_argument("--trace", help="write OpenTelemetry spans to this JSON Lines file")
    r.set_defaults(func=cmd_run)

    g = sub.add_parser("gate", help="fail if a run regressed against a baseline")
    g.add_argument("--baseline", required=True)
    g.add_argument("--current", required=True)
    g.add_argument(
        "--method",
        choices=["paired", "overlap"],
        default="paired",
        help="paired by task (default), or the older interval-overlap rule",
    )
    g.add_argument("--alpha", type=float, default=gate.ALPHA)
    g.add_argument(
        "--min-effect",
        type=float,
        default=gate.MIN_EFFECT,
        help="smallest mean drop that counts, as a fraction (0.05 = 5 points)",
    )
    g.set_defaults(func=cmd_gate)

    s = sub.add_parser("split", help="check the frozen split is the seeded draw it claims")
    s.add_argument("--benchmark", required=True)
    s.add_argument("--seed", type=int, required=True)
    s.add_argument(
        "--sampled", choices=["dev", "heldout"], required=True, help="which split was drawn"
    )
    s.set_defaults(func=cmd_split)

    w = sub.add_parser("power", help="simulate which drops the gate detects")
    w.add_argument("--tasks", type=int, default=20)
    w.add_argument("--trials", type=int, nargs="+", default=[1, 3, 5])
    w.add_argument("--base-rate", type=float, default=0.9)
    w.add_argument("--drops", type=float, nargs="+", default=[0, 0.05, 0.1, 0.15, 0.2, 0.3])
    w.add_argument("--sims", type=int, default=1000)
    w.set_defaults(func=cmd_power)

    p = sub.add_parser("report", help="print the Markdown summary of a result file")
    p.add_argument("result")
    p.set_defaults(func=cmd_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s"
    )
    code: int = args.func(args)
    return code


if __name__ == "__main__":
    sys.exit(main())
