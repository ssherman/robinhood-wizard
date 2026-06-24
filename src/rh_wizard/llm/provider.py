"""Build a provider-agnostic StructuredLlm from Settings (spec §5: provider-agnostic model
config). OpenAI is the v1 provider; the Anthropic branch is a declared seam.
"""

from __future__ import annotations

import os

from rh_wizard.config.settings import Settings
from rh_wizard.llm.base import LlmError, RetryingLlm, StructuredLlm
from rh_wizard.llm.strands_llm import StrandsLlm


def build_model(settings: Settings) -> object:
    provider = settings.model_provider.lower()
    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise LlmError("OPENAI_API_KEY is not set (the research/plan LLM key).")
        # NOTE: verify ctor against the installed strands.models.openai.OpenAIModel.
        from strands.models.openai import OpenAIModel

        return OpenAIModel(client_args={"api_key": api_key}, model_id=settings.model_id)
    if provider == "anthropic":
        raise LlmError("anthropic provider is a Phase 4b seam — not wired yet.")
    raise LlmError(f"unknown model provider '{settings.model_provider}'")


def build_llm(settings: Settings) -> StructuredLlm:
    return RetryingLlm(StrandsLlm(build_model(settings)))
