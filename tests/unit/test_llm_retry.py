import pydantic
import pytest

from rh_wizard.llm.base import LlmError, RetryingLlm, StructuredLlm


class Out(pydantic.BaseModel):
    value: int


class _Flaky:
    def __init__(self, fail_times):
        self.calls = 0
        self._fail = fail_times

    def generate(self, output_model, prompt, system=""):
        self.calls += 1
        if self.calls <= self._fail:
            raise ValueError("invalid structured output")
        return output_model(value=self.calls)


def test_retrying_llm_is_a_structured_llm():
    assert isinstance(RetryingLlm(_Flaky(0)), StructuredLlm)


def test_succeeds_after_retries():
    flaky = _Flaky(fail_times=2)
    out = RetryingLlm(flaky, max_retries=2).generate(Out, "p")
    assert out.value == 3  # 2 failures then success
    assert flaky.calls == 3


def test_aborts_after_max_retries():
    flaky = _Flaky(fail_times=5)
    with pytest.raises(LlmError):
        RetryingLlm(flaky, max_retries=2).generate(Out, "p")
    assert flaky.calls == 3  # initial + 2 retries
