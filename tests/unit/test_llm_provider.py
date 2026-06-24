import pytest

from rh_wizard.config.settings import Settings
from rh_wizard.llm.base import LlmError
from rh_wizard.llm.provider import build_model


def test_unknown_provider_raises():
    with pytest.raises(LlmError):
        build_model(Settings(model_provider="nope", model_id="x"))


def test_openai_requires_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LlmError):
        build_model(Settings(model_provider="openai", model_id="gpt-5.5"))


def test_anthropic_seam_not_wired_yet():
    with pytest.raises(LlmError):
        build_model(Settings(model_provider="anthropic", model_id="claude-opus-4-8"))
