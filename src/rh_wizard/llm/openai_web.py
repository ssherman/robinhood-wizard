"""OpenAI web-search research LLM (Phase 4b-2). Calls the OpenAI Responses API directly with
the hosted ``web_search`` tool and structured output, because Strands' structured_output path
drops tools. This is the only research module that imports the OpenAI SDK. The API key is read
from the environment and never logged."""

from __future__ import annotations

import os
from typing import TypeVar

import pydantic

from rh_wizard.config.settings import Settings
from rh_wizard.llm.base import LlmError
from rh_wizard.models.research import Source

T = TypeVar("T", bound=pydantic.BaseModel)


def _extract_sources(response: object) -> list[Source]:
    """Collect de-duplicated url_citation annotations from a Responses API result."""
    sources: list[Source] = []
    seen: set[str] = set()
    for item in getattr(response, "output", None) or []:
        if getattr(item, "type", None) != "message":
            continue
        for content in getattr(item, "content", None) or []:
            for ann in getattr(content, "annotations", None) or []:
                if getattr(ann, "type", None) != "url_citation":
                    continue
                url = getattr(ann, "url", None)
                if url and url not in seen:
                    seen.add(url)
                    title = (getattr(ann, "title", "") or "").strip()
                    sources.append(Source(title=title, url=url))
    return sources


class OpenAiWebSearchLlm:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def research(
        self, output_model: type[T], prompt: str, system: str = ""
    ) -> tuple[T, list[Source]]:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise LlmError("OPENAI_API_KEY is not set (the research/plan LLM key).")
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.responses.parse(
            model=self._settings.model_id,
            input=prompt,
            instructions=system or None,
            tools=[{"type": "web_search"}],
            text_format=output_model,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise LlmError("OpenAI Responses API returned no parsed output.")
        return parsed, _extract_sources(response)
