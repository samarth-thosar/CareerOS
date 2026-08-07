"""FakeLLMProvider -- returns a scripted response without calling any real model."""
from __future__ import annotations

from careeros.application.ports.llm_provider import LLMResponse, PromptSpec


class FakeLLMProvider:
    def __init__(self, response: LLMResponse) -> None:
        self._response = response
        self.received_prompts: list[PromptSpec] = []

    async def complete(self, prompt: PromptSpec) -> LLMResponse:
        self.received_prompts.append(prompt)
        return self._response
