"""LLMProvider port -- the LLM subsystem's only entry point.

`PromptSpec` and `LLMResponse` are model-agnostic; a concrete adapter (e.g. OllamaProvider) owns whatever
chat-template translation its backend needs. No prompt template or model-specific logic is allowed to live
outside a concrete adapter -- the LLM must remain fully swappable by construction.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class PromptSpec:
    system_prompt: str
    user_prompt: str
    response_schema: dict[str, Any] | None = None
    temperature: float = 0.2


@dataclass(slots=True)
class LLMResponse:
    text: str
    parsed: dict[str, Any] | None
    model_used: str


class LLMProvider(Protocol):
    async def complete(self, prompt: PromptSpec) -> LLMResponse: ...
