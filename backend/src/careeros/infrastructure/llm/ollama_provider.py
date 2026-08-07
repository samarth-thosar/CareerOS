"""OllamaProvider -- local, free LLM backend adapter (default model: qwen3:8b).

Implements the LLMProvider port against a local Ollama instance. All model-specific handling lives here, so
callers only ever build a model-agnostic `PromptSpec`:

* **Thinking mode.** Reasoning models such as Qwen3 emit a chain of thought by default. Measured on qwen3:8b,
  disabling it cut a scoring call from ~98s to ~64s, and CareerOS never uses the reasoning text -- it stores
  the model's `narrative` field instead. Ollama returns thought in a separate `thinking` field, but older
  builds and other models inline `<think>...</think>` in the content, so that is stripped defensively too.
* **keep_alive.** Without it Ollama can unload the model between calls and pay the load cost again on the
  next one, which dominates when scoring a backlog one job at a time.
* **num_predict.** Caps output length so a model that starts rambling cannot stall a batch indefinitely.
"""
from __future__ import annotations

import json
import logging
import re

import httpx

from careeros.application.ports.llm_provider import LLMResponse, PromptSpec

logger = logging.getLogger(__name__)

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class LLMRequestError(RuntimeError):
    """Raised when the model backend cannot be reached or returns an error response."""


class OllamaProvider:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout_seconds: float = 300.0,
        keep_alive: str = "10m",
        max_output_tokens: int = 800,
        disable_thinking: bool = True,
        client_factory: type[httpx.AsyncClient] = httpx.AsyncClient,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._keep_alive = keep_alive
        self._max_output_tokens = max_output_tokens
        self._disable_thinking = disable_thinking
        self._client_factory = client_factory

    async def complete(self, prompt: PromptSpec) -> LLMResponse:
        payload: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": prompt.system_prompt},
                {"role": "user", "content": prompt.user_prompt},
            ],
            "stream": False,
            "keep_alive": self._keep_alive,
            "options": {
                "temperature": prompt.temperature,
                # The prompt decides its own budget when it knows it needs more than the default; truncation
                # here shows up as unparseable JSON, which is easy to misread as the model misbehaving.
                "num_predict": prompt.max_output_tokens or self._max_output_tokens,
            },
        }
        if prompt.response_schema is not None:
            payload["format"] = prompt.response_schema
        if self._disable_thinking:
            payload["think"] = False

        try:
            async with self._client_factory(timeout=self._timeout_seconds) as client:
                response = await client.post(f"{self._base_url}/api/chat", json=payload)
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPError as error:
            raise LLMRequestError(f"Ollama request failed: {error}") from error

        text = _strip_thinking(body.get("message", {}).get("content", ""))
        parsed = _parse_json(text) if prompt.response_schema is not None else None

        if parsed is None and body.get("done_reason") == "length":
            # Distinguish "ran out of output budget" from "produced nonsense"; they look identical downstream
            # but only one is fixed by raising PromptSpec.max_output_tokens.
            logger.warning(
                "Model output hit the %d-token limit and was truncated; raise max_output_tokens for this prompt",
                prompt.max_output_tokens or self._max_output_tokens,
            )

        return LLMResponse(text=text, parsed=parsed, model_used=self._model)


def _strip_thinking(content: str) -> str:
    """Remove any inline <think> block, for models/builds that don't split thought into its own field."""
    return _THINK_BLOCK.sub("", content or "").strip()


def _parse_json(text: str) -> dict | None:
    """Parse a JSON response, tolerating a model that wraps it in prose or a code fence.

    Returns None rather than raising: the caller decides whether an unparseable response is fatal, and has the
    context to log which job it was scoring.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fall back to the outermost {...} span, which recovers ```json fences and leading commentary.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse JSON from model response: %r", text[:200])
    return None
