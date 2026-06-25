from types import SimpleNamespace

import pytest

from rh_wizard.config.settings import Settings
from rh_wizard.llm.base import LlmError
from rh_wizard.llm.openai_web import OpenAiWebSearchLlm, _extract_sources
from rh_wizard.models.research import ResearchReport


def _ann(type_, url, title=""):
    return SimpleNamespace(type=type_, url=url, title=title)


def _fake_response(items):
    return SimpleNamespace(output=items)


def test_extract_sources_collects_dedup_url_citations():
    message = SimpleNamespace(
        type="message",
        content=[
            SimpleNamespace(
                annotations=[
                    _ann("url_citation", "https://a.com", "  A title \n"),
                    _ann("url_citation", "https://a.com", "dup"),  # duplicate url dropped
                    _ann("file_citation", "https://ignore.com", "x"),  # wrong type ignored
                    _ann("url_citation", "https://b.com", "B"),
                ]
            )
        ],
    )
    other = SimpleNamespace(type="web_search_call")  # non-message item ignored
    sources = _extract_sources(_fake_response([other, message]))
    assert [(s.title, s.url) for s in sources] == [
        ("A title", "https://a.com"),
        ("B", "https://b.com"),
    ]


def test_extract_sources_handles_no_annotations():
    msg = SimpleNamespace(type="message", content=[SimpleNamespace(annotations=None)])
    assert _extract_sources(_fake_response([msg])) == []


def test_research_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    llm = OpenAiWebSearchLlm(Settings())
    with pytest.raises(LlmError) as exc:
        llm.research(ResearchReport, "prompt", system="sys")
    assert "OPENAI_API_KEY" in str(exc.value)
