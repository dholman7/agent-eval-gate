# agent-eval-gate

A benchmark runner and CI gate for agents that write tests. It runs an agent on a fixed set of tasks, scores what it produced against a real app with seeded bugs, reports every rate with a 95% confidence interval, and fails a pull request only when results drop by more than run-to-run noise.

The shipped benchmark asks an agent to write Playwright API tests for one Gherkin scenario at a time of [vendor-intake-app](https://github.com/dholman7/vendor-intake-app), pinned to a specific commit.

## Results so far

Dev split, 1 trial per task. These two runs anchor the scale; model-backed agents land between them.

| Agent | Task success | Seeded bugs caught | Suites failing on correct code |
|---|---|---|---|
| `reference` (hand-written oracle) | 100% (12/12), CI 76–100% | 100% (12/12), CI 76–100% | 0% (0/12) |
| `existing-tests` (the repo's current API tests) | 0% (0/12), CI 0–24% | 0% (0/12), CI 0–24% | 0% (0/12) |
| `single-call` (one Claude call, no tools) | not run yet | | |

Twelve tasks give wide intervals. That's the point of reporting them: a 12/12 result is consistent with a true rate as low as 76%.

## How a trial is scored

1. The agent gets the scenario text and a private copy of the target repo, and writes test files.
2. The files are type-checked and run against the **correct** app. Every test must pass, and at least one passing test must carry the task's tag (for example `@VEN-01`).
3. Only if that clean run passes, each seeded bug for the task is applied to the app, the app restarts on a fresh database, and the tests run again. A bug is caught if any test fails.

A suite that fails on correct code gets no credit for catching bugs. Otherwise a broken suite would "catch" everything.

## Benchmark design

Fixed before any agent was scored, so the benchmark can't be tuned to the agent.

| | |
|---|---|
| Tasks | 32, one per Gherkin scenario in the target repo |
| Split | 12 dev / 20 held-out, drawn once with a fixed seed and frozen in [`tasks.yaml`](benchmarks/vendor-intake/v1/tasks.yaml). Tune on dev; report held-out. |
| Bugs | 32 hand-written, in 11 categories (authorization, validation, dates, pagination, audit, ordering, state, security, status codes, contract, extraction). Each is an exact text replacement, applied only while scoring. They live in this repo, never in the target, so the agent under test can't read them. |
| Validity | `aeg validate` proves each bug's text matches exactly once, every reference test passes on correct code, and every bug is caught by the reference test of each task it targets. CI runs it on every push. |
| Contamination | The target app was written in October 2026, so its tasks can't be in any model's training data. |

### Metrics

| Metric | Meaning |
|---|---|
| Task success | Type-checks, passes on correct code, and covers the task's tag |
| pass^k | Share of tasks where all k trials succeed (consistency, not best-of-k) |
| Seeded bugs caught | Caught bugs ÷ (trials × bugs per task) |
| Suites failing on correct code | False alarms: a test that fails without a bug |
| Cost, agent time | Per trial, with bootstrap intervals |

Rates use Wilson score intervals, which behave sensibly at 0%, 100%, and small n.

### The gate

`aeg gate` fails only when intervals don't overlap in the bad direction: the current upper bound is below the baseline's lower bound (for false alarms, the reverse). Overlap passes. With tens of trials, a few points of movement is noise, and a gate that fails on noise gets turned off.

## Use it

```bash
uv sync
uv run aeg validate                                   # prove the benchmark is sound (about 2.5 min)
uv run aeg run --agent reference --split dev          # score an agent
uv run aeg gate --baseline baselines/reference-dev.json --current results/latest.json
```

Plug in any agent as a shell command:

```bash
uv run aeg run --agent my-agent --command "python my_agent.py" --split dev --trials 5
```

The command receives `AEG_TASK` (task JSON: scenario text, required tag, test directory), `AEG_WORKSPACE` (a private repo copy), and `AEG_OUTPUT` (where to write `*.ts` files). It may write `AEG_OUTPUT/usage.json` with token counts, cost, and model. Live runs are recorded under `recordings/`; `--replay` scores them again without calling the agent, which is how CI stays free and deterministic.

### The one-call Claude baseline

```bash
uv sync --extra claude
uv run aeg run --agent single-call --command "python -m agent_eval_gate.baselines.single_call" --split dev
```

Uses `claude-opus-5-5` at medium effort (`AEG_MODEL` and `AEG_EFFORT` override). Server-side refusal fallback is on, and every result records the model that actually answered. Estimated, not yet measured: about $0.10–0.15 per trial (roughly 15k input and 3k output tokens), so one pass over the dev split should stay under $2. The report shows the measured cost.

### GitHub Action

```yaml
- uses: dholman7/agent-eval-gate@main
  with:
    agent: my-agent
    replay: "true"              # score committed recordings; no model calls in CI
    baseline: baselines/my-agent-dev.json
```

The run's Markdown summary goes to the job summary, and OpenTelemetry spans (GenAI semantic-convention attributes) go to a JSON Lines trace file.

## Not in v1

- **Model-graded acceptance-criteria scoring.** Planned with agreement against hand labels (Cohen's κ) published before it counts toward any claim. v1 scores coverage deterministically, by tag.
- **Mutation-tool bugs** (mutmut). All 32 bugs are hand-written; adding generated mutants, kept only when a reference test catches them, removes the risk that the bug author unconsciously picks easy targets.
- **Live model results.** The `single-call` baseline is built and unit-tested against a stub; it runs as soon as an API key is configured.

## Layout

```
src/agent_eval_gate/     runner, scoring, stats, gate, telemetry, CLI
  baselines/single_call  one-call Claude baseline
benchmarks/vendor-intake/v1/
  benchmark.yaml         target repo, pinned ref, how to start the app and run tests
  tasks.yaml             32 tasks with frozen splits
  bugs.yaml              32 seeded bugs
  reference/             reference test per task, plus shared helpers
baselines/               stored results the gate compares against
action.yml               composite GitHub Action
```

## License

[MIT](LICENSE)
