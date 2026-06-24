"""The structured-output target models (ResearchReport, TradePlan) must emit JSON
schemas that OpenAI's structured-output validator accepts. Pydantic renders ``Decimal``
with an anchored lookaround regex (``^(?!...)...$``); OpenAI rejects regex lookaround, so
any Decimal field would break the research/plan stages. These guards fail loudly if a
Decimal (or any lookaround pattern) sneaks back into an LLM-output model.
"""

from decimal import Decimal

from rh_wizard.models.plan import TradeIntent, TradePlan
from rh_wizard.models.research import Candidate, ResearchReport

# Regex lookaround constructs that OpenAI structured output does not support.
_LOOKAROUND = ("(?=", "(?!", "(?<=", "(?<!")


def _patterns(node):
    if isinstance(node, dict):
        pat = node.get("pattern")
        if isinstance(pat, str):
            yield pat
        for value in node.values():
            yield from _patterns(value)
    elif isinstance(node, list):
        for value in node:
            yield from _patterns(value)


def _lookaround_patterns(model):
    return [
        p
        for p in _patterns(model.model_json_schema())
        if any(tok in p for tok in _LOOKAROUND)
    ]


def test_research_report_schema_has_no_lookaround():
    assert _lookaround_patterns(ResearchReport) == []


def test_trade_plan_schema_has_no_lookaround():
    assert _lookaround_patterns(TradePlan) == []


def test_llm_decimal_fields_still_coerce_to_decimal():
    # The schema fix must not change runtime semantics: values are still Decimal.
    assert Candidate(symbol="AAPL", conviction="0.7").conviction == Decimal("0.7")
    intent = TradeIntent(side="buy", symbol="AAPL", quantity="10", limit_price="190.50")
    assert intent.quantity == Decimal("10")
    assert intent.limit_price == Decimal("190.50")
