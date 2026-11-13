# 2. Seed bugs by mutation testing, chosen by code

Status: accepted, 2026-11-12 (backfilled: adopted in v3)

## Context

v1 and v2's 32 seeded bugs were written by hand, by the same person who wrote the tasks, the reference tests, and the agent. That author's sense of a "realistic" bug can drift toward bugs the agent happens to catch. Hand bugs also come one per idea, so some tasks get a sharp bug and others a blunt one.

## Decision

v3 adds bugs chosen by code. `aeg mutants`:

1. **Applies standard operators** at every eligible token of the target's backend source: comparison flips (`<`/`<=`, `==`/`!=`), `and`/`or`, booleans, a dropped `not`, and HTTP status codes.
2. **Runs every mutant against all of the benchmark's reference tests,** giving a kill matrix of which tasks catch which mutant.
3. **Keeps only discriminating mutants:** ones caught by at least 1 task and at most a quarter of them. A mutant caught by every task usually just crashes the app, and one caught by none is often equivalent to the original.
4. **Draws up to 2 per task with a fixed seed.** The selection is reproducible, and nobody picks.

The kill matrix is committed next to `mutants.yaml`, so anyone can check the selection. Hand-written bugs stay for the dev tasks they were written for.

## Evidence

- **On vendor-intake-app, 97 mutants across 17 backend files.** 35 survive every reference test, a 64% mutation score for the references. 23 were kept, and every task has at least one bug.
- **CI validates them like the hand-written ones,** checking that each is caught by its task's reference. That check found a mutant caught on one machine and not another. The cause was the references, which checked an audit trail's contents but not that the trail was the vendor's own, and they were tightened. A mutant that passes only by chance is a weak reference, not a weak bug.

## Alternatives considered

- **mutmut or cosmic-ray.** Both generate mutants, but neither selects them by a kill matrix across tasks. The operators are a short table, and a custom selector is the point.
- **Keep every surviving mutant as a "hard" bug.** No reference test catches those, so an agent couldn't be scored on them fairly.

## Consequences

- **Bug counts per task are now uneven but justified:** they follow what the references can distinguish.
- **The 35 survivors are a backlog for the references,** not for the benchmark. Some are equivalent mutants, and the rest are behavior no task covers yet.
