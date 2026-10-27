"""The Claude baseline, exercised against a stub client so tests never call the API."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("anthropic")

from agent_eval_gate.baselines import single_call

TASK = {
    "task_id": "VEN-01",
    "story": "Scenario: Create a vendor\n",
    "required_tag": "@VEN-01",
    "test_dir": "e2e/api/generated",
}


class StubMessages:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.response


def _client(text: str, stop_reason: str = "end_turn", model: str = "claude-opus-5-5") -> Any:
    response = SimpleNamespace(
        model=model,
        stop_reason=stop_reason,
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=text),
        ],
        usage=SimpleNamespace(input_tokens=10_000, output_tokens=2_000, cache_read_input_tokens=0),
    )
    return SimpleNamespace(beta=SimpleNamespace(messages=StubMessages(response)))


def test_prompt_includes_context_files_and_the_tag(tmp_path: Path) -> None:
    (tmp_path / "e2e" / "fixtures").mkdir(parents=True)
    (tmp_path / "e2e" / "fixtures" / "index.ts").write_text("export const USERS = {};")

    system, user = single_call.build_prompt(TASK, tmp_path)

    assert "@VEN-01" in system and "e2e/api/generated/VEN-01.spec.ts" in system
    assert '<file path="e2e/fixtures/index.ts">' in user
    assert "openapi.json" not in user  # missing files are skipped, not invented
    assert "Scenario: Create a vendor" in user


def test_dev_profile_is_the_default_and_uses_the_cheap_model() -> None:
    assert single_call.PROFILE == "dev"
    assert (single_call.MODEL, single_call.EFFORT) == ("claude-haiku-5-5", "low")


def test_haiku_requests_carry_no_fallback() -> None:
    # Haiku 5.5 has no server-side refusal fallback; sending one would be rejected.
    params = single_call.request_params("system", "user")

    assert params["model"] == "claude-haiku-5-5"
    assert "fallbacks" not in params and "betas" not in params


def test_generate_extracts_code_records_served_model_and_prices_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(single_call, "MODEL", "claude-opus-5-5")
    client = _client(
        "Here:\n```ts\ntest('x', { tag: '@VEN-01' }, async () => {});\n```", model="claude-opus-4-8"
    )

    result = single_call.generate(client, "system", "user")

    assert result.code is not None and "@VEN-01" in result.code
    assert result.model == "claude-opus-4-8"  # a fallback served it; priced at its own rate
    assert result.cost_usd == pytest.approx((10_000 * 5.00 + 2_000 * 25.00) / 1_000_000)
    call = client.beta.messages.calls[0]
    assert call["model"] == single_call.MODEL
    assert call["fallbacks"] == "default"
    assert "thinking" not in call and "temperature" not in call


@pytest.mark.parametrize(
    ("text", "stop_reason", "error"),
    [
        ("No code here.", "end_turn", "no ts code block in response"),
        ("", "refusal", "refused"),
        ("```ts\npartial", "max_tokens", "hit max_tokens before finishing"),
    ],
)
def test_generate_reports_why_there_is_no_usable_file(
    text: str, stop_reason: str, error: str
) -> None:
    result = single_call.generate(_client(text, stop_reason), "system", "user")

    assert result.code is None
    assert result.error == error
