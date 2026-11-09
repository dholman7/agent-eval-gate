"""How large a drop the gate catches, by simulation, so its sensitivity is stated, not assumed.

Each simulated benchmark draws a true success probability per task from a Beta distribution
with mean `base_rate`: real agents have tasks they always pass and tasks they sometimes fail,
and that spread is what a paired test exploits. A baseline run and a current run are then drawn
with every task's probability lowered by `drop` in the current one. The detection rate at
`drop=0` is the false-alarm rate.
"""

import random
from fractions import Fraction

from agent_eval_gate.gate import ALPHA, MIN_EFFECT, Method, is_regression, paired
from agent_eval_gate.stats import wilson

# Beta(base_rate * SPREAD, (1 - base_rate) * SPREAD): at 0.9, task rates have a spread (sd) of
# about 0.13, with most tasks near 1. Lower means more varied tasks.
SPREAD = 4.0


def detection_rate(
    tasks: int,
    trials: int,
    base_rate: float,
    drop: float,
    method: Method,
    sims: int = 1000,
    seed: int = 0,
    alpha: float = ALPHA,
    min_effect: float = MIN_EFFECT,
) -> float:
    rng = random.Random(seed)  # noqa: S311 - reproducible simulation, not security
    hits = 0
    for _ in range(sims):
        probs = [
            rng.betavariate(base_rate * SPREAD, (1 - base_rate) * SPREAD) for _ in range(tasks)
        ]
        base = [sum(rng.random() < p for _ in range(trials)) for p in probs]
        cur = [sum(rng.random() < max(0.0, p - drop) for _ in range(trials)) for p in probs]
        if method == "paired":
            diffs, p = paired(
                {str(i): Fraction(b, trials) for i, b in enumerate(base)},
                {str(i): Fraction(c, trials) for i, c in enumerate(cur)},
                higher_is_better=True,
            )
            hits += is_regression(diffs, p, True, alpha, min_effect)
        else:
            hits += wilson(sum(cur), tasks * trials).high < wilson(sum(base), tasks * trials).low
    return hits / sims


def table(
    tasks: int, trial_counts: list[int], base_rate: float, drops: list[float], sims: int
) -> str:
    """Markdown: rows are drops, columns are trial counts, cells are paired / overlap rates."""
    header = "| True drop | " + " | ".join(f"k={k}: paired / overlap" for k in trial_counts) + " |"
    lines = [header, "|---|" + "---|" * len(trial_counts)]
    for drop in drops:
        cells = [
            f"{detection_rate(tasks, k, base_rate, drop, 'paired', sims):.0%} / "
            f"{detection_rate(tasks, k, base_rate, drop, 'overlap', sims):.0%}"
            for k in trial_counts
        ]
        label = "0 (false alarms)" if drop == 0 else f"{drop * 100:g} pts"
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
