"""Tests for OllamaProvider's request shaping and response handling, against a stubbed HTTP client.

Covers the model-specific quirks the adapter exists to absorb: thinking-mode output, JSON wrapped in prose or
code fences, and backend errors surfacing as a typed failure.
"""
from __future__ import annotations

import httpx
import pytest

from careeros.application.ports.llm_provider import PromptSpec
from careeros.infrastructure.llm.ollama_provider import LLMRequestError, OllamaProvider

SCHEMA = {"type": "object", "properties": {"score": {"type": "integer"}}, "required": ["score"]}


def _client_returning(
    content: str, status_code: int = 200, done_reason: str | None = None
) -> tuple[type[httpx.AsyncClient], list[dict]]:
    """Stub client returning `content`, plus a list that captures the request bodies sent."""
    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured.append(json.loads(request.content))
        if status_code != 200:
            return httpx.Response(status_code, json={"error": "boom"})
        body: dict = {"message": {"role": "assistant", "content": content}}
        if done_reason is not None:
            body["done_reason"] = done_reason
        return httpx.Response(200, json=body)

    class StubClient(httpx.AsyncClient):
        def __init__(self, **kwargs) -> None:
            kwargs.pop("timeout", None)
            super().__init__(transport=httpx.MockTransport(handler), **kwargs)

    return StubClient, captured


def _prompt(with_schema: bool = True) -> PromptSpec:
    return PromptSpec(
        system_prompt="system",
        user_prompt="user",
        response_schema=SCHEMA if with_schema else None,
        temperature=0.0,
    )


class TestRequestShaping:
    async def test_disables_thinking_and_sets_keep_alive_and_output_cap(self) -> None:
        client, captured = _client_returning('{"score": 70}')
        provider = OllamaProvider("http://x", "qwen3:8b", keep_alive="5m", max_output_tokens=123,
                                  client_factory=client)

        await provider.complete(_prompt())

        body = captured[0]
        assert body["think"] is False
        assert body["keep_alive"] == "5m"
        assert body["options"]["num_predict"] == 123
        assert body["options"]["temperature"] == 0.0

    async def test_thinking_can_be_left_enabled(self) -> None:
        client, captured = _client_returning('{"score": 70}')
        provider = OllamaProvider("http://x", "m", disable_thinking=False, client_factory=client)

        await provider.complete(_prompt())

        assert "think" not in captured[0]

    async def test_prompt_output_budget_overrides_the_provider_default(self) -> None:
        # Regression: one global cap suited scoring and silently truncated tailoring into unparseable JSON.
        client, captured = _client_returning('{"score": 70}')
        provider = OllamaProvider("http://x", "m", max_output_tokens=800, client_factory=client)

        await provider.complete(
            PromptSpec(system_prompt="s", user_prompt="u", response_schema=SCHEMA, max_output_tokens=3000)
        )

        assert captured[0]["options"]["num_predict"] == 3000

    async def test_provider_default_applies_when_the_prompt_sets_no_budget(self) -> None:
        client, captured = _client_returning('{"score": 70}')
        provider = OllamaProvider("http://x", "m", max_output_tokens=800, client_factory=client)

        await provider.complete(_prompt())

        assert captured[0]["options"]["num_predict"] == 800

    async def test_truncated_output_is_logged_as_a_budget_problem(self, caplog) -> None:
        client, _ = _client_returning('{"summary": "cut off mid-str', done_reason="length")
        provider = OllamaProvider("http://x", "m", client_factory=client)

        with caplog.at_level("WARNING"):
            response = await provider.complete(_prompt())

        assert response.parsed is None
        assert any("truncated" in record.message for record in caplog.records)

    async def test_schema_is_forwarded_as_the_format_constraint(self) -> None:
        client, captured = _client_returning('{"score": 70}')
        provider = OllamaProvider("http://x", "m", client_factory=client)

        await provider.complete(_prompt())

        assert captured[0]["format"] == SCHEMA

    async def test_no_format_sent_when_no_schema_requested(self) -> None:
        client, captured = _client_returning("free text")
        provider = OllamaProvider("http://x", "m", client_factory=client)

        await provider.complete(_prompt(with_schema=False))

        assert "format" not in captured[0]


class TestResponseHandling:
    async def test_parses_clean_json(self) -> None:
        client, _ = _client_returning('{"score": 88}')
        provider = OllamaProvider("http://x", "qwen3:8b", client_factory=client)

        response = await provider.complete(_prompt())

        assert response.parsed == {"score": 88}
        assert response.model_used == "qwen3:8b"

    async def test_strips_inline_thinking_blocks(self) -> None:
        client, _ = _client_returning('<think>Let me consider...</think>{"score": 42}')
        provider = OllamaProvider("http://x", "m", client_factory=client)

        response = await provider.complete(_prompt())

        assert response.parsed == {"score": 42}
        assert "<think>" not in response.text

    async def test_recovers_json_from_a_code_fence(self) -> None:
        client, _ = _client_returning('Here you go:\n```json\n{"score": 55}\n```')
        provider = OllamaProvider("http://x", "m", client_factory=client)

        assert (await provider.complete(_prompt())).parsed == {"score": 55}

    async def test_unparseable_response_yields_none_rather_than_raising(self) -> None:
        # The caller decides severity; it knows which job was being scored.
        client, _ = _client_returning("I cannot help with that.")
        provider = OllamaProvider("http://x", "m", client_factory=client)

        response = await provider.complete(_prompt())

        assert response.parsed is None
        assert response.text == "I cannot help with that."

    async def test_no_parsing_attempted_without_a_schema(self) -> None:
        client, _ = _client_returning('{"score": 1}')
        provider = OllamaProvider("http://x", "m", client_factory=client)

        assert (await provider.complete(_prompt(with_schema=False))).parsed is None


async def test_backend_error_becomes_a_typed_failure() -> None:
    client, _ = _client_returning("", status_code=500)
    provider = OllamaProvider("http://x", "m", client_factory=client)

    with pytest.raises(LLMRequestError):
        await provider.complete(_prompt())
