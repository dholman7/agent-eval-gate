# agent-eval-gate

A benchmark runner and CI gate for agents that write tests. It runs an agent on a fixed set of tasks, scores what it produced against a real app with seeded bugs, reports every rate with a 95% confidence interval, and fails a pull request only when results drop by more than run-to-run noise.

The shipped benchmark asks an agent to write Playwright API tests for one Gherkin scenario at a time of [vendor-intake-app](https://github.com/dholman7/vendor-intake-app), pinned to a specific commit.

## Results

**Held-out split** (20 tasks), Claude Haiku 5.5 for the model-backed agents, 3 trials per task:

| Agent | Trials succeeded | All 3 trials succeed | Seeded bugs caught | Suites failing on correct code | Cost per trial |
|---|---|---|---|---|---|
| `reference` (hand-written oracle) | 100% (20/20)* | 100% | 100% (24/24)* | 0% | – |
| [Storywright](https://github.com/dholman7/storywright) v0.2 (read, write, run, repair) | 97% (58/60), CI 89–99% | 95% (19/20) | 97% (70/72), CI 90–99% | 3% (2/60) | $0.0028 |
| `single-call-dev` (one call, no tools) | 60% (36/60), CI 47–71% | 55% (11/20) | 60% (43/72), CI 48–70% | 39% (23/59) | $0.0018 |
| `existing-tests` (the repo's current API tests) | 0% (0/20)* | 0% | 17% (4/24)* | 0% | – |

\* Deterministic agents, run once: every trial would be identical.

Storywright v0.2 on Claude Opus 5.5 (1 trial per task): 100% (20/20, CI 84–100%) of tasks, 100% (24/24) of bugs caught, no suites failing on correct code, $0.091 per trial.

Storywright's interval sits entirely above the single call's, so the difference isn't noise. Its prompts were tuned on dev, and its repo tools were added after an earlier version's held-out score was seen, so its numbers come from fresh trials but aren't a blind result. The held-out tasks are easier on average than the dev tasks (the single call scores 60% here against 17% on dev), which is why agents are only compared within a split.

**Known benchmark issue (REV-03).** The scenario states exact confidences ("lowest confidence 0.40") that the app never produces: it scores an unparseable field 0.30. The reference test checks order only, but an agent that holds the scenario's numbers, as Storywright did in two trials, reports a defect. Both of Storywright's held-out failures are this case. The scenario text needs fixing in the target repo, which means a v2 of the benchmark; v1 stays frozen.

**Dev split** (12 tasks), 1 trial per task. Storywright's prompts were tuned here (83%, 10/12), so its dev number isn't a fair comparison and isn't listed.

| Agent | Task success | Seeded bugs caught | Suites failing on correct code |
|---|---|---|---|
| `reference` (hand-written oracle) | 100% (12/12), CI 76–100% | 100% (12/12), CI 76–100% | 0% (0/12) |
| `existing-tests` (the repo's current API tests) | 0% (0/12), CI 0–24% | 0% (0/12), CI 0–24% | 0% (0/12) |
| `single-call-report` (one Claude Opus 5.5 call, no tools) | 50% (6/12), CI 25–75% | 50% (6/12), CI 25–75% | 42% (5/12), CI 19–68% |
| `single-call-dev` (one Claude Haiku 5.5 call, no tools) | 17% (2/12), CI 5–45% | 17% (2/12), CI 5–45% | 83% (10/12), CI 55–95% |

Twelve tasks give wide intervals. That's the point of reporting them: a 12/12 result is consistent with a true rate as low as 76%.

**Why the one-call baseline fails.** Its tests are mostly well-formed but never ran before being submitted. Nine of the ten failures create a vendor with a reserved `.test` email address, which the app rejects with 422. The seeded accounts in the repo's fixtures use `.test`, so the model copied the pattern. Most of its tests also don't wait for background extraction. Running the tests once and reading the error would fix both, which is the gap an agent with a verify-and-repair loop should close. The Haiku run cost $0.023 for all 12 trials; the Opus run cost $1.04.

Opus makes the same `.test` mistake less often, but it shows why bugs caught is scored separately from tests passing. For DOC-03 ("fields that cannot be parsed get low confidence") it built a PDF in code and uploaded that. The extraction stub doesn't read PDFs, so every field came back empty with zero confidence and the assertions passed. The date was never parsed, so the seeded bug in the date parser went uncaught: a test that passes for the wrong reason.

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

`AEG_PROFILE` picks the model, and the cheap one is the default so routine runs cost almost nothing:

| Profile | Model and effort | Use for |
|---|---|---|
| `dev` (default) | `claude-haiku-5-5`, low | Iterating on prompts and the harness |
| `report` | `claude-opus-5-5`, medium | Numbers you publish |

`AEG_MODEL` and `AEG_EFFORT` override either part. On models that support it (Opus 5.5, Sonnet 5.5), server-side refusal fallback is on, and every result records the model that actually answered. The report shows measured cost per trial.

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
