"""`aeg` command line: validate a benchmark, run an agent, gate against a baseline."""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Literal

from agent_eval_gate import benchmark, gate, results, runner, telemetry, validate
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
    base = results.RunResult.model_validate_json(Path(args.baseline).read_text())
    current = results.RunResult.model_validate_json(Path(args.current).read_text())
    try:
        checks = gate.compare(base, current)
    except gate.IncomparableRuns as exc:
        print(f"Can't compare these runs: {exc}", file=sys.stderr)
        return 2
    _write_summary(gate.markdown(checks))
    return 1 if any(c.regressed for c in checks) else 0


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
    g.set_defaults(func=cmd_gate)

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
