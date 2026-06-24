"""Shared field types for models used as LLM structured-output targets.

Pydantic renders ``Decimal`` in JSON Schema with an anchored regex that uses lookaround
(``^(?!^[-+.]*$)...$``). OpenAI's structured-output (json_schema) validator rejects regex
lookaround, so a model carrying a plain ``Decimal`` field cannot be used as a research/plan
output target. ``LlmDecimal`` keeps full ``Decimal`` runtime semantics (validation,
serialization, exact arithmetic) but advertises a bare ``number`` JSON schema with no
pattern, so it is safe for structured output.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import WithJsonSchema

# A Decimal whose JSON schema is a bare ``number`` (no lookaround pattern). Runtime type and
# coercion are unchanged — only the emitted schema differs. Use for Decimal fields on any
# model passed to ``StructuredLlm.generate`` (ResearchReport, TradePlan, ...).
LlmDecimal = Annotated[Decimal, WithJsonSchema({"type": "number"})]
