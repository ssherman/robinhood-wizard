"""The structured-LLM seam (spec §5/§13).

``StructuredLlm.generate`` turns a prompt into a validated pydantic instance. ``StrandsLlm``
(separate module) is the only implementation that imports Strands/OpenAI; everything else
depends on this Protocol so the research/plan agents are testable without an LLM.
``RetryingLlm`` retries on any failure (invalid structured output, transient API error) then
raises ``LlmError`` so the cycle aborts cleanly (spec §13).
"""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

import pydantic

T = TypeVar("T", bound=pydantic.BaseModel)


class LlmError(Exception):
    pass


@runtime_checkable
class StructuredLlm(Protocol):
    def generate(self, output_model: type[T], prompt: str, system: str = "") -> T: ...


class RetryingLlm:
    """Decorate any StructuredLlm with retry-then-abort."""

    def __init__(self, inner: StructuredLlm, max_retries: int = 2) -> None:
        self._inner = inner
        self._max_retries = max_retries

    def generate(self, output_model: type[T], prompt: str, system: str = "") -> T:
        last: Exception | None = None
        for _ in range(self._max_retries + 1):
            try:
                return self._inner.generate(output_model, prompt, system)
            except Exception as exc:  # retry on invalid output / transient API error
                last = exc
        raise LlmError(
            f"LLM failed to produce valid {output_model.__name__} after "
            f"{self._max_retries + 1} attempt(s): {last}"
        ) from last
