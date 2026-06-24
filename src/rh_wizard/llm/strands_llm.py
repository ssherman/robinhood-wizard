"""The single Strands-aware adapter: build a Strands Agent on the given model and get a
schema-validated pydantic instance back via ``structured_output``. All Strands/OpenAI
specifics live here; the rest of the codebase depends only on the ``StructuredLlm`` Protocol.
"""

from __future__ import annotations

from typing import TypeVar

import pydantic

T = TypeVar("T", bound=pydantic.BaseModel)


class StrandsLlm:
    def __init__(self, model: object) -> None:
        self._model = model

    def generate(self, output_model: type[T], prompt: str, system: str = "") -> T:
        from strands import Agent

        agent = Agent(model=self._model, system_prompt=system or None)
        return agent.structured_output(output_model, prompt)
