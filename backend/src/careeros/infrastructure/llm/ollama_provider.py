"""OllamaProvider -- local, free LLM backend adapter (default model: qwen3:8b).

Implements the LLMProvider port with a real HTTP call to a local Ollama instance. No prompt-template or
scoring-specific logic lives here -- callers build a model-agnostic PromptSpec; this adapter translates it
into Ollama's chat API shape. See docs/architecture/decisions/0005-zero-paid-services-constraint.md and
docs/architecture/02-ports-and-interfaces.md.
"""
from __future__ import annotations

import json

import httpx

from careeros.application.ports.llm_provider import LLMResponse, PromptSpec


class OllamaProvider:
    def __init__(self, base_url: str, model: str, timeout_seconds: float = 120.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds

    async def complete(self, prompt: PromptSpec) -> LLMResponse:
        payload: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": prompt.system_prompt},
                {"role": "user", "content": prompt.user_prompt},
            ],
            "stream": False,
            "options": {"temperature": prompt.temperature},
        }
        if prompt.response_schema is not None:
            payload["format"] = prompt.response_schema

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(f"{self._base_url}/api/chat", json=payload)
            response.raise_for_status()
            body = response.json()

        text = body.get("message", {}).get("content", "")
        parsed: dict | None = None
        if prompt.response_schema is not None:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None

        return LLMResponse(text=text, parsed=parsed, model_used=self._model)
