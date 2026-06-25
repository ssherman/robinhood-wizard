import pytest

from rh_wizard.llm.base import LlmError
from rh_wizard.llm.web_search import RetryingWebSearchLlm, WebSearchLlm
from rh_wizard.models.research import ResearchReport, Source


class FlakyLlm:
    def __init__(self, fail_times):
        self.calls = 0
        self._fail_times = fail_times

    def research(self, output_model, prompt, system=""):
        self.calls += 1
        if self.calls <= self._fail_times:
            raise RuntimeError("transient")
        return ResearchReport(summary="ok"), [Source(url="https://x")]


def test_retries_then_succeeds():
    inner = FlakyLlm(fail_times=2)
    report, sources = RetryingWebSearchLlm(inner).research(ResearchReport, "p", system="s")
    assert report.summary == "ok"
    assert [s.url for s in sources] == ["https://x"]
    assert inner.calls == 3


def test_raises_llmerror_after_exhausting_retries():
    inner = FlakyLlm(fail_times=99)
    with pytest.raises(LlmError) as exc:
        RetryingWebSearchLlm(inner, max_retries=1).research(ResearchReport, "p")
    assert "ResearchReport" in str(exc.value)
    assert inner.calls == 2


def test_protocol_is_runtime_checkable():
    assert isinstance(FlakyLlm(0), WebSearchLlm)
