# agent-eval-gate design

## Context

Agents that write tests get changed often: a prompt, a model, a tool. Each change needs an answer to "did it get worse?" that holds up to a skeptical reviewer, and is cheap enough to ask on every pull request. Most agent evals give a score from one run, on tasks the agent was tuned on, graded by the model's own claims. This harness exists to give a better answer.

## Goals

- **Scores that mean something.** A generated test counts only if it type-checks, passes on the real app, carries the task's tag, and fails when a seeded bug is present.
- **Honest uncertainty.** Every rate gets a 95% Wilson interval, and comparisons pair by task ([ADR 0001](adr/0001-paired-gate.md)).
- **Blind held-out numbers.** Tasks are frozen before any agent sees them. Dev tasks are for tuning; held-out tasks are for reporting.
- **Free and deterministic in CI.** Live runs are recorded, and CI replays them without calling a model.
- **Agent-agnostic.** Any command that writes test files can be scored, including a general coding agent.

## Non-goals

- **Grading test quality by opinion.** No LLM judge decides whether a test is good. Catching seeded bugs is the measure.
- **Benchmarks for other app shapes.** One target app with real behavior beats several toy ones; the harness is generic, but the shipped benchmark isn't.

## Architecture

```
benchmark (tasks, bugs, references, pinned target ref)
   └─ aeg run ──> workspace copy per trial ──> agent writes tests ──> score:
                    typecheck, run on clean app, run under each seeded bug
   └─ results JSON + OTel trace ──> aeg gate (paired) / agent-telemetry
```

| Part | What it does |
|---|---|
| Workspace | Clones the target at a pinned commit once, then gives each trial a private copy. Seeded bugs are applied to the base during scoring and restored, under a lock, so two processes can't score each other's bugs. |
| Validation | `aeg validate` proves every reference passes on clean code and catches each of its bugs. CI runs it, so a benchmark can't silently rot. |
| Bugs | Hand-written for v1 and v2. v3 adds mutation bugs chosen by a kill matrix ([ADR 0002](adr/0002-mutation-bugs.md)). |
| Gate | A paired, one-sided sign-flip test per metric. It fails only when p < 0.05 and the drop is at least 5 points. `aeg power` reports what size of drop it can see. |
| Red team | `aeg attack` plants prompt injections in the agent's copy and checks deterministic oracles, with unplanted controls. |

## Options considered

| Option | Why not |
|---|---|
| Interval-overlap gating | Equivalent to α ≈ 0.005, and it ignores pairing. It caught a 20-point drop 47% of the time against the paired test's 87%. |
| Model-graded success | Not reproducible, and it grades the claim instead of the behavior. |
| Tasks sampled fresh each run | Comparisons need the same tasks. Blindness comes from freezing, not resampling. |

## Failure modes

| Failure | Guard |
|---|---|
| A reference that passes by luck, not by design | CI validation across machines. One was found this way and tightened. |
| Held-out tasks leak into tuning | Versioned benchmarks. v3's held-out tasks were committed before any agent ran on them. |
| A rate-limited run reads as a clean result | Attack reports count agent errors. The red-team runner treats a limited run as an error. |
| The harness changes what agents see | Fixed and disclosed: scoring used to delete the target's example tests. |
| Small task counts | Intervals and `aeg power` say what a run can and can't show, and README claims stay within them. |

## Cost model

Scoring is local and free. Live agent runs cost what the agent costs. A Storywright held-out run (15 tasks × 3 trials) is about $0.14 on Haiku and $4.20 on Opus at the v3 per-trial estimates. CI replays recordings, so it never calls a model.

## Metrics

Per trial:

- success (type-checks, passes on correct code, tagged);
- the seeded bugs caught;
- whether it fails on correct code;
- cost, duration, and token and cache usage, all also in the trace.

Per run: those as rates with intervals, and pass^k (every trial of a task succeeds).
