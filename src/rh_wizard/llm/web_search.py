"""The web-search LLM seam (Phase 4b-2). Like ``StructuredLlm`` but the model may call a
web-search tool while producing the structured output, and the call also returns the source
citations. ``OpenAiWebSearchLlm`` (separate module) is the only implementation that imports
the OpenAI SDK; the research agent depends on this Protocol so it is testable without an LLM.
``RetryingWebSearchLlm`` retries then raises ``LlmError`` so the cycle aborts cleanly."""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

import pydantic

from rh_wizard.llm.base import LlmError
from rh_wizard.models.research import Source

T = TypeVar("T", bound=pydantic.BaseModel)


@runtime_checkable
class WebSearchLlm(Protocol):
    def research(
        self, output_model: type[T], prompt: str, system: str = ""
    ) -> tuple[T, list[Source]]: ...


class RetryingWebSearchLlm:
    """Decorate any WebSearchLlm with retry-then-abort."""

    def __init__(self, inner: WebSearchLlm, max_retries: int = 2) -> None:
        self._inner = inner
        self._max_retries = max_retries

    def research(
        self, output_model: type[T], prompt: str, system: str = ""
    ) -> tuple[T, list[Source]]:
        last: Exception | None = None
        for _ in range(self._max_retries + 1):
            try:
                return self._inner.research(output_model, prompt, system)
            except Exception as exc:  # retry on invalid output / transient API error
                last = exc
        raise LlmError(
            f"web-search LLM failed to produce valid {output_model.__name__} after "
            f"{self._max_retries + 1} attempt(s): {last}"
        ) from last
