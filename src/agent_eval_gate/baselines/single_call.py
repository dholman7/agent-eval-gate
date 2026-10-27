"""Baseline: one Claude call, no tools. Story plus repo context in, one Playwright spec out.

Runs as a CommandAgent: `python -m agent_eval_gate.baselines.single_call`. It answers
"how much of the work does a single well-prompted call do?", the bar a real agent must beat.
"""

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# (model, effort) per profile. `dev` is the default so routine runs stay cheap; publish numbers
# from `report`. AEG_MODEL and AEG_EFFORT override either part.
PROFILES: dict[str, tuple[str, str]] = {
    "dev": ("claude-haiku-5-5", "low"),
    "report": ("claude-opus-5-5", "medium"),
}
PROFILE = os.environ.get("AEG_PROFILE", "dev")
if PROFILE not in PROFILES:
    raise SystemExit(f"AEG_PROFILE must be one of {sorted(PROFILES)}, got {PROFILE!r}")
MODEL = os.environ.get("AEG_MODEL", PROFILES[PROFILE][0])
EFFORT = os.environ.get("AEG_EFFORT", PROFILES[PROFILE][1])
MAX_TOKENS = 16000

# Models that accept server-side refusal fallback (`fallbacks: "default"`). Haiku 5.5 has none.
FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5"}

# USD per million tokens (input, output, cache read), from the Claude API pricing table
# (2026-10-06). Cache-read rates for Opus 5, Opus 4.8, and Haiku 5.5 aren't listed there and
# assume the usual 10% of input; this baseline sets no cache breakpoints, so they don't apply.
# Haiku 5.5 is priced for prompts up to 100K tokens, which these prompts stay well under.
PRICES: dict[str, tuple[float, float, float]] = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "claude-opus-5": (5.00, 25.00, 0.50),
    "claude-opus-4-8": (5.00, 25.00, 0.50),
}

# Repo files given as context, relative to the workspace root. Missing files are skipped.
CONTEXT_FILES = (
    "openapi.json",
    "e2e/fixtures/index.ts",
    "e2e/playwright.config.ts",
    "e2e/api/auth.spec.ts",
)

SYSTEM = """You write Playwright API tests in TypeScript for an existing repository.

Rules:
- Write exactly one test file. Return it as a single ```ts fenced code block and nothing else.
- The file lives at {test_dir}/{task_id}.spec.ts. Import test helpers from "../../fixtures".
- Every test must carry the tag {tag}, e.g. test("...", {{ tag: "{tag}" }}, async (...) => ...).
- Test the scenario's behavior through the HTTP API only. Assert status codes, error codes,
  and response fields the scenario names.
- Tests share one database and run in parallel: give anything you create a unique name.
- Never weaken an assertion to make a test pass. Test what the scenario specifies."""


@dataclass
class Generation:
    code: str | None
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    error: str | None = None

    @property
    def cost_usd(self) -> float:
        prices = PRICES.get(self.model) or PRICES.get(MODEL)
        if prices is None:
            raise KeyError(f"no price for {self.model!r}; add it to PRICES")
        if self.model not in PRICES:
            print(f"warning: no price for {self.model}; using {MODEL} rates", file=sys.stderr)
        price_in, price_out, price_cache = prices
        return (
            self.input_tokens * price_in
            + self.output_tokens * price_out
            + self.cache_read_tokens * price_cache
        ) / 1_000_000


def build_prompt(task: dict[str, Any], workspace: Path) -> tuple[str, str]:
    system = SYSTEM.format(
        test_dir=task["test_dir"], task_id=task["task_id"], tag=task["required_tag"]
    )
    sections = []
    for relative in CONTEXT_FILES:
        path = workspace / relative
        if path.is_file():
            sections.append(f'<file path="{relative}">\n{path.read_text()}\n</file>')
    user = (
        "\n\n".join(sections)
        + f"\n\nWrite the tests for this scenario:\n<scenario>\n{task['story']}</scenario>"
    )
    return system, user


_FENCE = re.compile(r"```(?:ts|typescript)\s*\n(.*?)```", re.DOTALL)


def extract_code(text: str) -> str | None:
    blocks = _FENCE.findall(text)
    return blocks[-1] if blocks else None


def request_params(system: str, user: str) -> dict[str, Any]:
    params: dict[str, Any] = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": {"effort": EFFORT},
    }
    if MODEL in FALLBACK_MODELS:
        params |= {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    return params


def generate(client: Any, system: str, user: str) -> Generation:
    """One request. Where fallback is on, the model that actually answered is recorded."""
    import anthropic

    try:
        response = client.beta.messages.create(**request_params(system, user))
    except anthropic.APIStatusError as exc:
        return Generation(None, MODEL, 0, 0, 0, error=f"API {exc.status_code}: {exc.message}")
    except anthropic.APIConnectionError as exc:
        return Generation(None, MODEL, 0, 0, 0, error=f"connection error: {exc}")

    usage = response.usage
    generation = Generation(
        code=None,
        model=response.model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", None) or 0,
    )
    if response.stop_reason == "refusal":
        generation.error = "refused"
        return generation
    if response.stop_reason == "max_tokens":
        generation.error = "hit max_tokens before finishing"
    text = "".join(block.text for block in response.content if block.type == "text")
    generation.code = extract_code(text)
    if generation.code is None and generation.error is None:
        generation.error = "no ts code block in response"
    return generation


def main() -> int:
    import anthropic

    task = json.loads(Path(os.environ["AEG_TASK"]).read_text())
    workspace = Path(os.environ["AEG_WORKSPACE"])
    output = Path(os.environ["AEG_OUTPUT"])

    system, user = build_prompt(task, workspace)
    result = generate(anthropic.Anthropic(), system, user)
    if result.code is not None:
        (output / f"{task['task_id']}.spec.ts").write_text(result.code)
    (output / "usage.json").write_text(
        json.dumps(
            {
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cost_usd": round(result.cost_usd, 6),
                "model": result.model,
            }
        )
    )
    if result.error:
        print(result.error, file=sys.stderr)
    return 0 if result.code is not None else 1


if __name__ == "__main__":
    sys.exit(main())
