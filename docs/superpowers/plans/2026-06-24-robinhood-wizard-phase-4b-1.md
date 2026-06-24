# Robinhood Wizard — Phase 4b-1 Implementation Plan (Agentic Core: LLM Research + Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. **This plan was written in a prior session; execute it fresh.** Start by reading the project memory and this whole plan, then run the subagent-driven flow (per-task brief → implementer → spec/quality review → fix loop), ending with an opus whole-branch review + `finishing-a-development-branch`.

**Goal:** Replace the Phase 4a deterministic stub brain with a **real LLM `Researcher` and `Planner`** behind the existing Phase 4a `Researcher`/`Planner` Protocols — reasoning over the Phase 3 `MarketContext` (quotes + fundamentals) + `strategy.intent`, emitting a schema-validated `ResearchReport`/`TradePlan` via Strands structured output, with retry-on-invalid then a clean abort (spec §13). The deterministic cycle, risk engine, and DryRun render/journal are unchanged.

**Architecture:** Provider-agnostic `llm/` built on the **Strands Agents SDK** (the project's committed choice — model-agnostic, MCP-native). A one-class `StrandsLlm` adapter wraps `Agent(model).structured_output(PydanticModel, prompt)`; a `RetryingLlm` decorator adds retry/abort; `build_llm(settings)` maps `Settings.model_provider` → a Strands model (OpenAI now; Anthropic seam left). The new `LlmResearcher`/`LlmPlanner` depend only on a tiny `StructuredLlm` Protocol — so **every Strands/OpenAI detail lives in one adapter** and the agents are fully offline-testable with a `FakeStructuredLlm`.

**Tech Stack:** Python 3.12, `pydantic` v2, **`strands-agents`** (installed, 1.44.0) + **`openai`** (NEW dependency — Strands' OpenAI provider needs it), `typer`/`rich` (CLI), `pytest`, `ruff`, `uv`.

## Design Decisions (review — flag if you disagree)

1. **OpenAI is the first provider** (user decision, 2026-06-23). `Settings.model_provider` defaults to `"openai"` and `model_id` to `"gpt-5.5"`. **⚠️ Confirm the exact current OpenAI model-id string before the live run** — it is a config value, never hard-coded in logic; if `gpt-5.5` is wrong, the user edits `~/.rh-wizard/config.yaml`. The provider mapping leaves a clean Anthropic seam (`claude-*`) for later.
2. **Build on Strands, not the raw OpenAI SDK.** The approved master spec (§3 decision 7, §5 `llm/`) committed to Strands for model-agnosticism + MCP-native integration. We use `strands.models.openai.OpenAIModel` + `Agent.structured_output`. (The `claude-api` skill does not apply — we are not writing Anthropic calls.)
3. **`StructuredLlm` Protocol is the seam.** `generate(output_model, prompt, system) -> T` (T = a pydantic model). `StrandsLlm` is the only class that imports Strands; `RetryingLlm` decorates any `StructuredLlm`. `LlmResearcher`/`LlmPlanner` depend on the Protocol → unit-tested with a `FakeStructuredLlm`, **no LLM and no network in any unit test**.
4. **Retry then abort (spec §13).** `RetryingLlm` retries `max_retries` times on any exception (invalid structured output, API error), then raises `LlmError`. `run_cycle` already aborts cleanly on an exception in the research/plan stage? — NO: Phase 4a's `run_cycle` only wraps the *reconcile* prefix in try/except. **This plan adds a second try/except around the research→plan→vet stages** so an LLM failure aborts the cycle cleanly (status `aborted`, journaled) rather than crashing (Task 6).
5. **The LLM key is separate from Robinhood OAuth.** `OPENAI_API_KEY` comes from the environment (`.env`), read in `build_model`. Never logged.
6. **Deferred:** web/news search → Phase 4b-2 (the thematic-research vision); NL `strategy.intent` → structured-fields compiler → Phase 4c; universe discovery + allocation-aware planning → later. 4b-1's research reasons over the resolved structured data + the free-text `intent`.
7. **Stubs stay.** `StubResearcher`/`StubPlanner` remain (used by the cycle's offline tests and as a fallback); `cli/run.py` swaps to the `Llm*` versions for the real `wizard run`.

## Global Constraints

- **Python 3.12**; `from __future__ import annotations` at the top of every new module.
- **Lint/format:** ruff `select = ["E","F","I","UP","B"]`, `line-length = 100`; `uv run ruff check .` and `uv run ruff format --check .` green each task. (`typer.Argument(...)` defaults need `# noqa: B008`; `str, Enum` → `StrEnum`.)
- **Tests:** `uv run pytest` (`-q`, `pythonpath=["src"]`). **No network / no LLM / no broker in any unit test.** The LLM is faked via `FakeStructuredLlm`; the broker via `FakeBroker`; data via `FakeDataSource`. One opt-in live test behind `RH_WIZARD_LIVE=1` (also needs `OPENAI_API_KEY`).
- **Money/quantities are `Decimal`.** Never `float`.
- **Dependency direction:** `llm/` imports `models/` + `config/` + `strands`/`openai` only — never `cli/`, `core/`, `risk/`, `data/`, `memory/`. `research/`+`planning/` import `models/` + `llm/` (the Protocol) only. `core/` (the cycle) is untouched except Task 6's abort guard. Never import `cli/` from a non-cli module.
- **No secrets logged.** `OPENAI_API_KEY` is read from env and passed to the model; it must never appear in logs, journal, or rendered output.
- **Reuse existing models verbatim** (Phase 2/3/4a): `Strategy(id,name,intent,universe,signals_needed,cadence,risk_overrides)`; `Candidate(symbol,thesis,conviction)` + `ResearchReport(candidates,summary)`; `TradeIntent(side,symbol,quantity,amount,limit_price,rationale,confidence)` + `TradePlan(intents,rationale)`; `MarketContext(requested,symbols,unmet_signals,notes)` + `SymbolData(symbol,price,average_volume,market_cap,pe_ratio,pb_ratio,sector,industry,week_52_high,week_52_low,dividend_yield)`; `PortfolioState(account_number,positions,cash,buying_power,market_value,total_value,total_return_pct)`. The `Researcher` Protocol is `research(strategy, market, portfolio) -> ResearchReport`; the `Planner` Protocol is `plan(strategy, report, market, portfolio) -> TradePlan`.

**Branch:** `phase-4b-1` off `main` (sync `main` first — Phase 4a is merged at PR #5). PR at the end. Tasks 1–6 are offline-tested; Task 7 is the opt-in live run (needs a fresh OpenAI key + a cached Robinhood token).

---

## File Structure

**New files:**
- `src/rh_wizard/llm/__init__.py` (empty)
- `src/rh_wizard/llm/base.py` — `StructuredLlm` Protocol, `LlmError`, `RetryingLlm`.
- `src/rh_wizard/llm/strands_llm.py` — `StrandsLlm` (the only Strands-importing class).
- `src/rh_wizard/llm/provider.py` — `build_model`, `build_llm`.
- `src/rh_wizard/research/llm.py` — `LlmResearcher` + `_research_prompt`.
- `src/rh_wizard/planning/llm.py` — `LlmPlanner` + `_plan_prompt`.
- `tests/unit/test_llm_retry.py`, `test_llm_provider.py`, `test_research_llm.py`, `test_planning_llm.py`
- `tests/integration/test_live_research.py`

**Modified files:**
- `pyproject.toml` — add `openai` to `dependencies`; run `uv lock`.
- `.env.example` — add `OPENAI_API_KEY=`.
- `src/rh_wizard/config/settings.py` — defaults → `model_provider="openai"`, `model_id="gpt-5.5"`.
- `src/rh_wizard/core/cycle.py` — wrap research→plan→vet in a try/except → aborted run (Task 6).
- `src/rh_wizard/cli/run.py` — build + inject `LlmResearcher`/`LlmPlanner` via a patchable `_build_llm`.
- `tests/unit/test_cli_run.py` — monkeypatch `_build_llm` to a `FakeStructuredLlm`; add a research/plan helper. (Update the existing test so it stays offline.)
- `src/rh_wizard/config/paths.py` — (only if a key path helper is wanted; not required — env is read directly.)

---

### Task 1: Dependency + config — `openai`, env key, OpenAI defaults

Add the `openai` dependency, document `OPENAI_API_KEY`, and flip the `Settings` defaults to the OpenAI provider.

**Files:** Modify `pyproject.toml`, `.env.example`, `src/rh_wizard/config/settings.py`; Test `tests/unit/test_settings.py` (extend) or a new `tests/unit/test_llm_config.py`.

**Interfaces:** Produces `Settings()` with `model_provider == "openai"`, `model_id == "gpt-5.5"`.

- [ ] **Step 1: failing test** — new `tests/unit/test_llm_config.py`:
```python
from rh_wizard.config.settings import Settings, load_settings


def test_settings_default_openai_provider():
    s = Settings()
    assert s.model_provider == "openai"
    assert s.model_id == "gpt-5.5"


def test_settings_model_overridable(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("model_provider: anthropic\nmodel_id: claude-opus-4-8\n")
    s = load_settings(cfg)
    assert s.model_provider == "anthropic"
    assert s.model_id == "claude-opus-4-8"
```
- [ ] **Step 2:** run → FAIL (defaults are still `anthropic`/`claude-sonnet-4-6`).
- [ ] **Step 3:** In `config/settings.py` change the two defaults to `model_provider: str = "openai"` and `model_id: str = "gpt-5.5"`. In `pyproject.toml` add `"openai>=1.0"` to `[project] dependencies`; run `uv lock` (or `uv sync`) so `uv.lock` updates and `openai` installs into `.venv`. In `.env.example` add a line `OPENAI_API_KEY=` with a comment that it is the research/plan LLM key (separate from Robinhood OAuth).
- [ ] **Step 4:** run focused test → PASS; run full `uv run pytest` → green (note: any existing test asserting the old `claude-sonnet-4-6` default must be updated — check `tests/unit/test_settings.py`).
- [ ] **Step 5:** lint; `git add pyproject.toml uv.lock .env.example src/rh_wizard/config/settings.py tests/unit/test_llm_config.py` (+ any updated settings test); commit `feat: add openai dep + OPENAI_API_KEY; default LLM provider to openai`.

---

### Task 2: `StructuredLlm` Protocol + `RetryingLlm`

The seam every agent depends on, plus the retry/abort decorator (spec §13).

**Files:** Create `src/rh_wizard/llm/__init__.py` (empty), `src/rh_wizard/llm/base.py`; Test `tests/unit/test_llm_retry.py`.

**Interfaces:**
- `StructuredLlm` (`@runtime_checkable` Protocol): `generate(self, output_model: type[T], prompt: str, system: str = "") -> T` (T bound to `pydantic.BaseModel`).
- `LlmError(Exception)`.
- `RetryingLlm(inner: StructuredLlm, max_retries: int = 2)` implementing `StructuredLlm`.

- [ ] **Step 1: failing test** — `tests/unit/test_llm_retry.py`:
```python
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
    assert out.value == 3          # 2 failures then success
    assert flaky.calls == 3


def test_aborts_after_max_retries():
    flaky = _Flaky(fail_times=5)
    with pytest.raises(LlmError):
        RetryingLlm(flaky, max_retries=2).generate(Out, "p")
    assert flaky.calls == 3         # initial + 2 retries
```
- [ ] **Step 2:** run → FAIL (`ModuleNotFoundError: rh_wizard.llm`).
- [ ] **Step 3:** `llm/__init__.py` empty; `llm/base.py`:
```python
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
```
- [ ] **Step 4:** run → PASS (3). Full suite green.
- [ ] **Step 5:** lint; commit `feat: add StructuredLlm seam + RetryingLlm (retry-then-abort)`.

---

### Task 3: `StrandsLlm` adapter + provider builder

The one Strands/OpenAI-aware class, and `build_model`/`build_llm` from `Settings`.

**Files:** Create `src/rh_wizard/llm/strands_llm.py`, `src/rh_wizard/llm/provider.py`; Test `tests/unit/test_llm_provider.py`.

**Interfaces:**
- `StrandsLlm(model)` implementing `StructuredLlm` via `Agent(model, system_prompt=...).structured_output(output_model, prompt)`.
- `build_model(settings) -> object` (a Strands model); raises `LlmError` on missing key / unknown provider.
- `build_llm(settings) -> StructuredLlm` = `RetryingLlm(StrandsLlm(build_model(settings)))`.

> **Implementer note:** the exact `OpenAIModel.__init__` signature must be verified against the *installed* `strands.models.openai` after `openai` is installed (Task 1). The shape below (`client_args={"api_key": ...}, model_id=...`) is the documented Strands form; if the installed version differs, adapt the kwargs and say so in the report. `StrandsLlm` itself is exercised by the live test (Task 7), not a unit test (it needs the real SDK + key); the unit test here covers the provider-mapping logic only.

- [ ] **Step 1: failing test** — `tests/unit/test_llm_provider.py`:
```python
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
```
- [ ] **Step 2:** run → FAIL (`ModuleNotFoundError: rh_wizard.llm.provider`).
- [ ] **Step 3:** `llm/strands_llm.py`:
```python
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
```
`llm/provider.py`:
```python
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
```
- [ ] **Step 4:** run → PASS (3). Full suite green. (The OpenAI branch raises before importing `strands.models.openai` when the key is unset, so the test needs no `openai`/network.)
- [ ] **Step 5:** lint; commit `feat: add StrandsLlm adapter + build_llm provider (openai)`.

---

### Task 4: `LlmResearcher`

Real researcher: prompt from `strategy.intent` + resolved `MarketContext` + holdings → `ResearchReport`. Implements the Phase 4a `Researcher` Protocol.

**Files:** Create `src/rh_wizard/research/llm.py`; Test `tests/unit/test_research_llm.py`.

**Interfaces:** Consumes `StructuredLlm` (Task 2), `Strategy`/`MarketContext`/`PortfolioState`/`ResearchReport` (existing). Produces `LlmResearcher(llm)` with `research(strategy, market, portfolio) -> ResearchReport` (satisfies `research.base.Researcher`).

- [ ] **Step 1: failing test** — `tests/unit/test_research_llm.py`:
```python
from decimal import Decimal

from rh_wizard.models.market import MarketContext, SymbolData
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.research import Candidate, ResearchReport
from rh_wizard.models.strategy import Strategy
from rh_wizard.research.base import Researcher
from rh_wizard.research.llm import LlmResearcher


class FakeLlm:
    def __init__(self, report):
        self._report = report
        self.last_prompt = None
        self.last_system = None

    def generate(self, output_model, prompt, system=""):
        assert output_model is ResearchReport
        self.last_prompt = prompt
        self.last_system = system
        return self._report


def _market():
    return MarketContext(symbols={
        "AAPL": SymbolData(symbol="AAPL", price="190", pe_ratio="30", sector="Technology"),
    })


def _portfolio():
    return PortfolioState(account_number="A", positions=[], cash=Decimal("10000"),
                          buying_power=Decimal("10000"))


def test_llm_researcher_is_a_researcher():
    assert isinstance(LlmResearcher(FakeLlm(ResearchReport())), Researcher)


def test_research_builds_prompt_and_returns_report():
    report = ResearchReport(candidates=[Candidate(symbol="AAPL")], summary="ok")
    fake = FakeLlm(report)
    strategy = Strategy(id="m", name="M", intent="buy quality tech", universe=["AAPL"])
    out = LlmResearcher(fake).research(strategy, _market(), _portfolio())
    assert out is report
    assert "buy quality tech" in fake.last_prompt          # intent in prompt
    assert "AAPL" in fake.last_prompt                       # resolved symbol in prompt
    assert fake.last_system                                 # non-empty system prompt
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** `research/llm.py`:
```python
"""LLM-backed research stage (spec §5). Replaces the Phase 4a stub behind the same
``Researcher`` Protocol. It investigates the strategy's universe against the resolved market
data and returns a structured ResearchReport; it cannot place orders.
"""

from __future__ import annotations

from rh_wizard.llm.base import StructuredLlm
from rh_wizard.models.market import MarketContext
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.research import ResearchReport
from rh_wizard.models.strategy import Strategy

RESEARCH_SYSTEM = (
    "You are a disciplined equity research analyst for a small, risk-managed account. "
    "Given a strategy thesis and current market data, identify which candidate tickers fit "
    "the thesis and assign each a brief rationale and a conviction from 0 to 1. Only use the "
    "data provided; do not invent prices or fundamentals. A deterministic risk engine will "
    "vet anything that is later proposed for trading — your job is research, not order sizing."
)


def _fmt_symbol(symbol: str, market: MarketContext) -> str:
    d = market.symbols.get(symbol)
    if d is None:
        return f"- {symbol}: (no market data resolved)"
    parts = [f"price={d.price}"]
    if d.pe_ratio is not None:
        parts.append(f"P/E={d.pe_ratio}")
    if d.market_cap is not None:
        parts.append(f"mktcap={d.market_cap}")
    if d.sector:
        parts.append(f"sector={d.sector}")
    if d.industry:
        parts.append(f"industry={d.industry}")
    return f"- {symbol}: " + ", ".join(parts)


def _research_prompt(strategy: Strategy, market: MarketContext, portfolio: PortfolioState) -> str:
    held = {p.symbol for p in portfolio.positions}
    lines = [
        f"Strategy: {strategy.name}",
        f"Thesis (free text): {strategy.intent or '(none provided)'}",
        "",
        "Candidate universe and resolved market data:",
        *[_fmt_symbol(s, market) for s in strategy.universe],
        "",
        f"Currently held: {', '.join(sorted(held)) or '(none)'}",
        f"Cash available: {portfolio.cash}",
    ]
    if market.unmet_signals:
        lines.append("Unmet signals (data gaps): " + ", ".join(s.value for s in market.unmet_signals))
    lines.append("")
    lines.append("Return a ResearchReport: candidates that fit the thesis (with thesis text "
                 "and conviction 0-1) plus a one-paragraph summary.")
    return "\n".join(lines)


class LlmResearcher:
    def __init__(self, llm: StructuredLlm) -> None:
        self._llm = llm

    def research(
        self, strategy: Strategy, market: MarketContext, portfolio: PortfolioState
    ) -> ResearchReport:
        prompt = _research_prompt(strategy, market, portfolio)
        return self._llm.generate(ResearchReport, prompt, system=RESEARCH_SYSTEM)
```
- [ ] **Step 4:** run → PASS (3). Full suite green.
- [ ] **Step 5:** lint; commit `feat: add LlmResearcher (structured ResearchReport from market data + intent)`.

---

### Task 5: `LlmPlanner`

Real planner: `ResearchReport` + market + portfolio → `TradePlan`. Implements the Phase 4a `Planner` Protocol. The system prompt steers it to propose **limit** orders **at/near the current price** (so they pass the slippage band) and to size conservatively — but the deterministic risk engine remains the hard gate.

**Files:** Create `src/rh_wizard/planning/llm.py`; Test `tests/unit/test_planning_llm.py`.

**Interfaces:** Consumes `StructuredLlm`, `Strategy`/`ResearchReport`/`MarketContext`/`PortfolioState`/`TradePlan` (existing). Produces `LlmPlanner(llm)` with `plan(strategy, report, market, portfolio) -> TradePlan` (satisfies `planning.base.Planner`).

- [ ] **Step 1: failing test** — `tests/unit/test_planning_llm.py`:
```python
from decimal import Decimal

from rh_wizard.models.market import MarketContext, SymbolData
from rh_wizard.models.plan import TradeIntent, TradePlan
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.research import Candidate, ResearchReport
from rh_wizard.models.strategy import Strategy
from rh_wizard.planning.base import Planner
from rh_wizard.planning.llm import LlmPlanner


class FakeLlm:
    def __init__(self, plan):
        self._plan = plan
        self.last_prompt = None

    def generate(self, output_model, prompt, system=""):
        assert output_model is TradePlan
        self.last_prompt = prompt
        return self._plan


def _market():
    return MarketContext(symbols={"AAPL": SymbolData(symbol="AAPL", price="190")})


def _portfolio():
    return PortfolioState(account_number="A", positions=[], cash=Decimal("10000"),
                          buying_power=Decimal("10000"))


def test_llm_planner_is_a_planner():
    assert isinstance(LlmPlanner(FakeLlm(TradePlan())), Planner)


def test_plan_passes_report_and_returns_plan():
    plan = TradePlan(intents=[
        TradeIntent(side="buy", symbol="AAPL", quantity="2", limit_price="190")
    ], rationale="thesis fit")
    fake = FakeLlm(plan)
    report = ResearchReport(candidates=[Candidate(symbol="AAPL", thesis="cheap")], summary="s")
    out = LlmPlanner(fake).plan(Strategy(id="m", name="M"), report, _market(), _portfolio())
    assert out is plan
    assert "AAPL" in fake.last_prompt        # candidate surfaced into the prompt
    assert "190" in fake.last_prompt         # current price available for limit pricing
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** `planning/llm.py`:
```python
"""LLM-backed plan stage (spec §5). Replaces the Phase 4a stub behind the same ``Planner``
Protocol. It turns a ResearchReport into a proposed TradePlan that must still survive the
deterministic risk engine. The prompt constrains it toward limit orders at the current price.
"""

from __future__ import annotations

from rh_wizard.llm.base import StructuredLlm
from rh_wizard.models.market import MarketContext
from rh_wizard.models.plan import TradePlan
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.research import ResearchReport
from rh_wizard.models.strategy import Strategy

PLAN_SYSTEM = (
    "You translate research into a concrete TradePlan for a small, risk-managed account. "
    "Rules: propose LIMIT orders only; set each limit price AT the current market price "
    "shown (orders far from the market are rejected); prefer a few high-conviction positions "
    "over many; never propose selling a symbol that is not currently held. A deterministic "
    "risk engine independently vets every intent for position size, cash reserve, liquidity, "
    "and slippage and will reject anything unsafe — do not try to bypass it."
)


def _candidate_lines(report: ResearchReport, market: MarketContext) -> list[str]:
    lines = []
    for c in report.candidates:
        d = market.symbols.get(c.symbol)
        price = d.price if d is not None else None
        conv = "" if c.conviction is None else f", conviction={c.conviction}"
        lines.append(f"- {c.symbol}: price={price}{conv} — {c.thesis or '(no thesis)'}")
    return lines


def _plan_prompt(
    strategy: Strategy, report: ResearchReport, market: MarketContext, portfolio: PortfolioState
) -> str:
    held = {p.symbol for p in portfolio.positions}
    lines = [
        f"Strategy: {strategy.name}",
        f"Thesis: {strategy.intent or '(none)'}",
        f"Research summary: {report.summary or '(none)'}",
        "",
        "Researched candidates (use the price shown as the limit price):",
        *_candidate_lines(report, market),
        "",
        f"Currently held: {', '.join(sorted(held)) or '(none)'}",
        f"Cash available: {portfolio.cash}",
        "",
        "Return a TradePlan of TradeIntents (side, symbol, quantity, limit_price, rationale).",
    ]
    return "\n".join(lines)


class LlmPlanner:
    def __init__(self, llm: StructuredLlm) -> None:
        self._llm = llm

    def plan(
        self,
        strategy: Strategy,
        report: ResearchReport,
        market: MarketContext,
        portfolio: PortfolioState,
    ) -> TradePlan:
        prompt = _plan_prompt(strategy, report, market, portfolio)
        return self._llm.generate(TradePlan, prompt, system=PLAN_SYSTEM)
```
- [ ] **Step 4:** run → PASS (3). Full suite green.
- [ ] **Step 5:** lint; commit `feat: add LlmPlanner (structured TradePlan from research)`.

---

### Task 6: Wire the cycle + CLI to the real LLM; abort cleanly on LLM failure

Two changes: (a) `core/cycle.py` — wrap the research→plan→vet stages so an LLM failure aborts the cycle cleanly (journaled), mirroring the reconcile abort; (b) `cli/run.py` — build the real `LlmResearcher`/`LlmPlanner` via a patchable `_build_llm`, and keep the CLI test offline by injecting a `FakeStructuredLlm`.

**Files:** Modify `src/rh_wizard/core/cycle.py`, `src/rh_wizard/cli/run.py`, `tests/unit/test_cli_run.py`; Test: extend `tests/unit/test_cycle.py` with an LLM-abort case.

**Interfaces:** `cli/run.py` gains `_build_llm(settings) -> StructuredLlm` (thin wrapper over `llm.provider.build_llm`, monkeypatched in tests). `run_cycle` unchanged in signature; its body gains a try/except around stages 6–8.

- [ ] **Step 1: failing tests.**
  In `tests/unit/test_cycle.py` add (reusing its existing `FakeBroker`/`FakeDataSource`/`_deps`):
```python
def test_cycle_aborts_when_research_raises():
    from rh_wizard.core.cycle import run_cycle
    from rh_wizard.memory.journal import SqliteJournal
    from rh_wizard.models.signals import Signal
    from rh_wizard.models.strategy import Strategy

    class BoomResearcher:
        def research(self, strategy, market, portfolio):
            raise RuntimeError("llm down")

    strategy = Strategy(id="m", name="M", universe=["AAPL"], signals_needed={Signal.PRICE})
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal)
        deps.researcher = BoomResearcher()
        with deps.broker:
            result = run_cycle(strategy, deps)
        assert result.run.status == "aborted"
        assert "llm down" in result.run.note
        assert result.vetted is None
        assert journal.recent_runs()[0].status == "aborted"
```
  In `tests/unit/test_cli_run.py`, update so `run_strategy` stays offline: monkeypatch the new `_build_llm` to a `FakeStructuredLlm` that returns a canned `ResearchReport` (candidate AAPL) and `TradePlan` (buy 1 AAPL @ price). Assert the rendered output still shows AAPL + "DryRun" + "no orders". (Add a small `FakeStructuredLlm` to the test that branches on `output_model`.)
- [ ] **Step 2:** run both → FAIL (cycle currently lets the research exception propagate; `_build_llm` doesn't exist).
- [ ] **Step 3:**
  In `core/cycle.py`, wrap stages 6–8 (research, plan, policy, vet). Replace the block from `report = deps.researcher.research(...)` through `vetted = vet(...)` with:
```python
    # Stages 6-8 (RESEARCH, PLAN, RISK) — an agentic-stage failure aborts cleanly (spec §13).
    try:
        report = deps.researcher.research(strategy, market, portfolio)
        plan = deps.planner.plan(strategy, report, market, portfolio)
        policy = build_effective_policy(
            deps.settings.risk, deps.settings.risk_ceiling, strategy.risk_overrides
        )
        vetted = vet(plan, policy, portfolio, market.to_symbol_risk())
    except Exception as exc:
        run = run.model_copy(
            update={"status": "aborted", "finished_at": _now(), "note": f"research/plan failed: {exc}"}
        )
        deps.journal.record_run(run)
        return CycleResult(run=run, portfolio=portfolio, market=market)
```
  (Keep the existing success path — `record_run` + `record_plan` + full `CycleResult` — after the try/except, unchanged.)
  In `cli/run.py`: add
```python
def _build_llm(settings):
    """Build the research/plan LLM (real path; patched in tests)."""
    from rh_wizard.llm.provider import build_llm

    return build_llm(settings)
```
  and in `run_strategy`, replace `researcher=StubResearcher(), planner=StubPlanner()` with:
```python
        llm = _build_llm(settings)
        deps = CycleDeps(
            broker=broker,
            settings=settings,
            resolver=resolver,
            researcher=LlmResearcher(llm),
            planner=LlmPlanner(llm),
            journal=journal,
        )
```
  Update imports in `cli/run.py` (drop the stub imports if now unused; add `from rh_wizard.research.llm import LlmResearcher` and `from rh_wizard.planning.llm import LlmPlanner`).
- [ ] **Step 4:** run the two updated test files → PASS; full `uv run pytest` green.
- [ ] **Step 5:** lint; commit `feat: run cycle with LLM research/plan; abort cleanly on agentic-stage failure`.

---

### Task 7: Opt-in live research+plan cycle (OpenAI)

Prove the full real cycle end-to-end against OpenAI + the live broker (DryRun, no orders). Opt-in behind `RH_WIZARD_LIVE=1` (also requires `OPENAI_API_KEY`).

**Files:** Create `tests/integration/test_live_research.py`.

- [ ] **Step 1: write the gated test:**
```python
"""Live, opt-in DryRun cycle with the REAL LLM research/plan agents (read-only — no orders).

Run explicitly (needs a cached Robinhood token AND OPENAI_API_KEY):
    RH_WIZARD_LIVE=1 uv run pytest tests/integration/test_live_research.py -v -s
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RH_WIZARD_LIVE") != "1",
    reason="set RH_WIZARD_LIVE=1 to run the live LLM research cycle",
)


def test_live_llm_dryrun_cycle(tmp_path):
    from rh_wizard.cli import auth
    from rh_wizard.cli.render import render_cycle_result
    from rh_wizard.config.settings import load_settings
    from rh_wizard.core.cycle import CycleDeps, run_cycle
    from rh_wizard.data.resolver import SignalResolver
    from rh_wizard.data.robinhood import RobinhoodDataSource
    from rh_wizard.llm.provider import build_llm
    from rh_wizard.memory.journal import SqliteJournal
    from rh_wizard.models.signals import Signal
    from rh_wizard.models.strategy import Strategy
    from rh_wizard.planning.llm import LlmPlanner
    from rh_wizard.research.llm import LlmResearcher

    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")

    settings = load_settings()
    strategy = Strategy(
        id="live-llm", name="Live LLM",
        intent="Prefer large-cap technology names with reasonable valuations.",
        universe=["AAPL", "MSFT", "NVDA"],
        signals_needed={Signal.PRICE, Signal.AVERAGE_VOLUME, Signal.MARKET_CAP},
    )
    broker = auth._build_broker(settings)
    resolver = SignalResolver([RobinhoodDataSource(broker)])
    llm = build_llm(settings)
    with broker, SqliteJournal(tmp_path / "wizard.db") as journal:
        deps = CycleDeps(broker=broker, settings=settings, resolver=resolver,
                         researcher=LlmResearcher(llm), planner=LlmPlanner(llm), journal=journal)
        result = run_cycle(strategy, deps)
        print("\n" + render_cycle_result(result))

    assert result.run.status in {"completed", "aborted"}  # never crashes
    if result.run.status == "completed":
        assert result.report is not None
        assert result.vetted is not None
```
- [ ] **Step 2:** `uv run pytest tests/integration/test_live_research.py -v` → 1 skipped. Full suite green; ruff clean.
- [ ] **Step 3:** commit `test: add opt-in live LLM research+plan DryRun cycle (skipped by default)`.

> The live run itself is executed during review **with the user** (it needs a fresh `OPENAI_API_KEY` and confirmation of the exact OpenAI model id). It is read-only (DryRun — no orders); confirm the model id in `~/.rh-wizard/config.yaml` first.

---

## Final Verification
- [ ] `uv run pytest && uv run ruff check . && uv run ruff format --check .` → green (live tests skipped without `RH_WIZARD_LIVE=1`).
- [ ] PR: `git push -u origin phase-4b-1 && gh pr create --title "Phase 4b-1: LLM research + plan agents (OpenAI via Strands)" --body "Replaces the Phase 4a stubs with real LlmResearcher/LlmPlanner behind the existing seams, via a provider-agnostic StructuredLlm built on Strands (OpenAI provider). Structured-output validated, retry-then-abort (§13). Web search → 4b-2; NL strategy compiler → 4c."`

## Self-Review (done during planning)
- **Spec coverage:** `llm/` provider-agnostic config (§5) → Tasks 1,3; research agent → §13 retry → Tasks 2,4,6; plan generator structured-output-validated → Task 5; cycle integration + clean abort (§13) → Task 6; offline fakes + opt-in live (§14) → all + Task 7. Web/NL-compiler explicitly deferred (4b-2/4c).
- **Type consistency:** `StructuredLlm.generate(output_model, prompt, system) -> T` defined Task 2, consumed identically in Tasks 3/4/5/6; `build_llm(settings) -> StructuredLlm` (Task 3) consumed by `_build_llm` (Task 6) + live test (Task 7); `LlmResearcher.research`/`LlmPlanner.plan` match the Phase 4a Protocols and the cycle's call sites.
- **Risks flagged inline:** the exact `OpenAIModel` ctor and the `gpt-5.5` model id must both be verified against the installed SDK / current OpenAI lineup before the live run — both are isolated (one adapter, one config value).
