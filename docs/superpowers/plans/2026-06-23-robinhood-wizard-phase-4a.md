# Robinhood Wizard — Phase 4a Implementation Plan (Deterministic DryRun Cycle)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the **deterministic DryRun trading cycle end-to-end** (spec §8 stages 1–9, 11–12) wiring together Phases 1–3 behind clean `Researcher`/`Planner` interfaces with a **stub brain**, so `wizard run <strategy>` produces and renders an auditable, risk-vetted `TradePlan` without ever placing an order — and the real LLM core slots in at Phase 4b without touching the skeleton.

**Architecture:** A `Strategy` (structured YAML) is loaded from a registry. `core/cycle.py`'s `run_cycle` is the deterministic skeleton: reconcile (Phase 1) → resolve signals (Phase 3) → `Researcher` → `Planner` → risk `vet` (Phase 2) → DryRun render + journal. The two agentic stages are `Protocol` seams with deterministic `StubResearcher`/`StubPlanner` implementations now; the LLM versions replace them in Phase 4b. No LLM and no order placement exist in 4a — every unit test runs offline.

**Tech Stack:** Python 3.12, `pydantic` v2, `Decimal` for money, `pyyaml`, `typer` + `rich` (CLI), `sqlite3` (journal), `pytest`, `ruff`, `uv`. No new third-party dependencies.

## Design Decisions (review these — flag if you disagree)

These resolve ambiguities in the spec's *indicative* interfaces (§6) and record the scoping choices agreed during brainstorming:

1. **Skeleton-first.** Phase 4a is the deterministic cycle with **stubbed** research/plan behind `Researcher`/`Planner` Protocols. Phase 4b replaces the stubs with real Strands LLM agents (+ the NL strategy compiler) — no skeleton change. (Spec §3 decision 8: "deterministic skeleton owns control flow; the LLM runs loose only inside research & plan-generation.")
2. **Strategies are structured YAML** in `~/.rh-wizard/strategies/*.yaml`. The free-text `Strategy.intent` field is **stored now** (it's where a thematic description like "20% rare-earth, 20% energy, 40% AI" lives) and handed to the research stage, but the NL→structured **compiler** is deferred to 4b, and **universe-discovery** (theme → tickers) is a later phase. 4a acts only on the explicit `universe` list.
3. **Universe = `strategy.universe ∪ current holdings`** (so existing positions are eligible for sells). A single line in the cycle — a future discovery stage replaces just that source.
4. **The stub brain is deliberately naive but live-runnable.** `StubResearcher` flags the resolved universe symbols as candidates (neutral theses); `StubPlanner` proposes a **1-share limit buy at the current price** of each candidate not already held. This exercises the full pipeline (liquidity/position/cash/deploy guardrails, DryRun render, journal) against real data, and is clearly labeled a stub. It is NOT a trading strategy.
5. **`mode` is a forward-seam, not a behavior switch yet.** `CycleMode` is a `StrEnum` with `DRY_RUN` plus declared-not-implemented `HUMAN_APPROVAL`/`AUTONOMOUS` seams. 4a has **no execution stage and no `OrderExecutor`** — those land in Phase 5. `wizard run` is always DryRun (no `--mode` flag until a second mode exists — YAGNI). This is a deliberate simplification of the brainstorm's "ExecutionPolicy seam": a one-implementation Protocol adds no value yet; the enum is the seam.
6. **Kill-switch (spec §8 step 4) stays deferred to Phase 6** (Phase 2 decision #3 carries the threshold but doesn't enforce). 4a's cycle has no kill-switch stage.
7. **`run_cycle` does not manage the broker context.** The caller (CLI / live test) wraps it in `with broker:` — mirroring `wizard positions`. The cycle assumes an already-connected broker. Pure-offline unit tests use a `FakeBroker` + a `FakeDataSource`-backed `SignalResolver`, so no network and no LLM run.
8. **Journal grows two tables** (`runs`, `plan_intents`) and two writers (`record_run`, `record_plan`) — the existing `trades` table is untouched. `record_plan` persists the **VettedPlan** (approved + rejected-with-reason) keyed by `run_id` — that is the auditable decision record (spec §6).

---

## Global Constraints

Every task implicitly includes these:

- **Python:** `requires-python = ">=3.12"`; ruff `target-version = "py312"`.
- **Lint/format:** ruff `select = ["E", "F", "I", "UP", "B"]`, `line-length = 100`. Every task ends green on `uv run ruff check .` and `uv run ruff format --check .`. (`str, Enum` triggers UP042 → use `StrEnum`; `typer.Argument(...)` defaults trigger B008 → `# noqa: B008` on that line, as in the existing `wizard data` command.)
- **Tests:** `uv run pytest` (configured `addopts = "-q"`, `pythonpath = ["src"]`, `testpaths = ["tests"]`). **No network / no LLM / no broker in any unit test** — the cycle is exercised with a `FakeBroker` + `FakeDataSource` + the stubs. The single live test is opt-in behind `RH_WIZARD_LIVE=1`.
- **Money/quantities are `Decimal`.** Never `float`. Construct from strings in tests.
- **Models use `pydantic.BaseModel` with `from __future__ import annotations`.** Input models that parse user/YAML data (`Strategy`) set `model_config = pydantic.ConfigDict(extra="forbid")`; output/bundle models do not.
- **Dependency direction:** `core/` may import `models/`, `strategies/`, `research/`, `planning/`, `risk/`, `data/`, `memory/`, `config/` — it is the orchestrator. `research/` and `planning/` import `models/` only (+ stdlib). `strategies/` imports `models/` + `config/`. Never import `cli/` from a non-cli module.
- **No new third-party dependencies.**
- **DryRun places no orders.** No code path in 4a calls `place_equity_order`/`review_equity_order`. A test asserts the cycle never touches an executor (there is none).

**Branch:** Create `phase-4a` off `main`. Open a PR at the end. Tasks 1–9 are covered by offline unit tests; Task 10 is the opt-in live `wizard run` DryRun smoke (needs a cached token from `wizard auth login`).

---

## File Structure

**New files:**
- `src/rh_wizard/models/strategy.py` — `Strategy`.
- `src/rh_wizard/models/research.py` — `Candidate`, `ResearchReport`.
- `src/rh_wizard/models/cycle.py` — `CycleMode`, `CycleRun`.
- `src/rh_wizard/strategies/__init__.py`, `strategies/registry.py` — `StrategyRegistry`, `StrategyNotFoundError`.
- `src/rh_wizard/research/__init__.py`, `research/base.py` (`Researcher`), `research/stub.py` (`StubResearcher`).
- `src/rh_wizard/planning/__init__.py`, `planning/base.py` (`Planner`), `planning/stub.py` (`StubPlanner`).
- `src/rh_wizard/core/__init__.py`, `core/cycle.py` — `CycleDeps`, `CycleResult`, `run_cycle`.
- `src/rh_wizard/cli/run.py` — `run_strategy`, `list_strategies`.
- `strategies.example/sample-momentum.yaml` — a committed example strategy.
- `tests/unit/test_models_strategy.py`, `test_models_research_cycle.py`, `test_strategy_registry.py`, `test_research_stub.py`, `test_planning_stub.py`, `test_journal_runs.py`, `test_cycle.py`, `test_render_cycle.py`, `test_cli_run.py`
- `tests/integration/test_live_run.py`

**Modified files:**
- `src/rh_wizard/config/paths.py` — add `strategies_dir()`.
- `src/rh_wizard/memory/journal.py` — add `runs` + `plan_intents` tables, `record_run`, `record_plan`, `recent_runs`.
- `src/rh_wizard/cli/render.py` — add `render_cycle_result`.
- `src/rh_wizard/cli/app.py` — register `run` and `strategies` commands.

---

### Task 1: `Strategy` model

The structured strategy (spec §7): free-text intent (stored for the future LLM/discovery stages), explicit universe, needed signals, cadence hint, embedded risk overrides.

**Files:**
- Create: `src/rh_wizard/models/strategy.py`
- Test: `tests/unit/test_models_strategy.py`

**Interfaces:**
- Consumes: `Signal` (`rh_wizard.models.signals`).
- Produces: `Strategy(id: str, name: str, intent: str = "", universe: list[str] = [], signals_needed: set[Signal] = set(), cadence: str | None = None, risk_overrides: dict[str, object] = {})`, `extra="forbid"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_models_strategy.py
import pydantic
import pytest

from rh_wizard.models.signals import Signal
from rh_wizard.models.strategy import Strategy


def test_strategy_minimal_defaults():
    s = Strategy(id="momentum", name="Momentum")
    assert s.id == "momentum"
    assert s.intent == ""
    assert s.universe == []
    assert s.signals_needed == set()
    assert s.cadence is None
    assert s.risk_overrides == {}


def test_strategy_coerces_signals_from_strings():
    s = Strategy(id="m", name="M", universe=["AAPL"], signals_needed=["price", "market_cap"])
    assert s.signals_needed == {Signal.PRICE, Signal.MARKET_CAP}


def test_strategy_holds_intent_and_overrides():
    s = Strategy(
        id="m", name="M", intent="20% energy, 40% AI", risk_overrides={"max_position_pct": "15"}
    )
    assert s.intent.startswith("20% energy")
    assert s.risk_overrides == {"max_position_pct": "15"}


def test_strategy_forbids_unknown_fields():
    with pytest.raises(pydantic.ValidationError):
        Strategy(id="m", name="M", bogus=1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_models_strategy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rh_wizard.models.strategy'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/rh_wizard/models/strategy.py
"""The strategy model (spec §7).

A ``Strategy`` is authored as structured YAML in ``~/.rh-wizard/strategies/``. ``intent`` is
free natural language (e.g. a thematic allocation) — stored now and handed to the research
stage; the NL→structured compiler and theme→ticker universe discovery come later. Phase 4a
acts only on the explicit ``universe`` list. ``risk_overrides`` is layered onto the global
defaults by the risk engine's ``build_effective_policy``.
"""

from __future__ import annotations

import pydantic

from rh_wizard.models.signals import Signal


class Strategy(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")

    id: str
    name: str
    intent: str = ""  # free-text thesis (used by the Phase 4b research agent)
    universe: list[str] = []  # explicit candidate tickers (Phase 4a)
    signals_needed: set[Signal] = set()  # signals the strategy wants resolved
    cadence: str | None = None  # hint only in v1 (e.g. "weekly")
    risk_overrides: dict[str, object] = {}  # merged onto global RiskPolicy defaults
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_models_strategy.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/models/strategy.py tests/unit/test_models_strategy.py
git commit -m "feat: add Strategy model"
```

---

### Task 2: `ResearchReport` + `CycleRun` models

The research stage's structured output and the per-run audit record.

**Files:**
- Create: `src/rh_wizard/models/research.py`
- Create: `src/rh_wizard/models/cycle.py`
- Test: `tests/unit/test_models_research_cycle.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Candidate(symbol: str, thesis: str = "", conviction: Decimal | None = None)`
  - `ResearchReport(candidates: list[Candidate] = [], summary: str = "")`
  - `CycleMode(StrEnum)` with members `DRY_RUN = "dryrun"`, `HUMAN_APPROVAL = "human_approval"`, `AUTONOMOUS = "autonomous"`.
  - `CycleRun(run_id: str, strategy_id: str, mode: str, started_at: str, finished_at: str | None = None, status: str = "completed", note: str = "")`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_models_research_cycle.py
from decimal import Decimal

from rh_wizard.models.cycle import CycleMode, CycleRun
from rh_wizard.models.research import Candidate, ResearchReport


def test_candidate_and_report_defaults():
    r = ResearchReport()
    assert r.candidates == []
    assert r.summary == ""
    c = Candidate(symbol="AAPL", thesis="cheap", conviction="0.7")
    assert c.conviction == Decimal("0.7")


def test_cycle_mode_values():
    assert CycleMode.DRY_RUN == "dryrun"
    assert CycleMode.HUMAN_APPROVAL.value == "human_approval"
    assert CycleMode.AUTONOMOUS.value == "autonomous"


def test_cycle_run_defaults_completed():
    run = CycleRun(run_id="r1", strategy_id="m", mode="dryrun", started_at="2026-06-23T00:00:00")
    assert run.status == "completed"
    assert run.finished_at is None
    assert run.note == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_models_research_cycle.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rh_wizard.models.research'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/rh_wizard/models/research.py
"""Research stage output (spec §7). The agent (stub in Phase 4a) returns candidate tickers
with a thesis and conviction; the planner turns this into a TradePlan."""

from __future__ import annotations

from decimal import Decimal

import pydantic


class Candidate(pydantic.BaseModel):
    symbol: str
    thesis: str = ""
    conviction: Decimal | None = None  # 0..1, optional


class ResearchReport(pydantic.BaseModel):
    candidates: list[Candidate] = []
    summary: str = ""
```

```python
# src/rh_wizard/models/cycle.py
"""Cycle audit models (spec §7/§8).

``CycleMode`` is the execution-mode seam (only ``DRY_RUN`` is implemented in Phase 4a;
``HUMAN_APPROVAL``/``AUTONOMOUS`` are declared seams for Phases 5/6). ``CycleRun`` is the
per-run audit record persisted by the journal.
"""

from __future__ import annotations

from enum import StrEnum

import pydantic


class CycleMode(StrEnum):
    DRY_RUN = "dryrun"
    HUMAN_APPROVAL = "human_approval"  # Phase 5 seam
    AUTONOMOUS = "autonomous"  # Phase 6 seam


class CycleRun(pydantic.BaseModel):
    run_id: str
    strategy_id: str
    mode: str
    started_at: str  # ISO timestamp
    finished_at: str | None = None
    status: str = "completed"  # completed | aborted
    note: str = ""  # abort reason / notes
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_models_research_cycle.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/models/research.py src/rh_wizard/models/cycle.py tests/unit/test_models_research_cycle.py
git commit -m "feat: add ResearchReport/Candidate and CycleMode/CycleRun models"
```

---

### Task 3: `StrategyRegistry` (YAML loading)

Load strategies from `~/.rh-wizard/strategies/*.yaml`; list available ids; raise a clear error when one is missing.

**Files:**
- Create: `src/rh_wizard/strategies/__init__.py` (empty)
- Create: `src/rh_wizard/strategies/registry.py`
- Modify: `src/rh_wizard/config/paths.py`
- Test: `tests/unit/test_strategy_registry.py`

**Interfaces:**
- Consumes: `Strategy` (Task 1), `paths` (`rh_wizard.config.paths`), `yaml`.
- Produces:
  - `paths.strategies_dir() -> Path` = `home_dir() / "strategies"`.
  - `StrategyNotFoundError(Exception)`.
  - `StrategyRegistry(directory: Path)` with `list() -> list[str]` (sorted yaml stems) and `load(strategy_id: str) -> Strategy`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_strategy_registry.py
import pytest

from rh_wizard.models.signals import Signal
from rh_wizard.strategies.registry import StrategyNotFoundError, StrategyRegistry


def _write(dirpath, name, text):
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / name).write_text(text)


def test_list_returns_sorted_stems(tmp_path):
    d = tmp_path / "strategies"
    _write(d, "b.yaml", "id: b\nname: B\n")
    _write(d, "a.yaml", "id: a\nname: A\n")
    assert StrategyRegistry(d).list() == ["a", "b"]


def test_list_empty_when_dir_missing(tmp_path):
    assert StrategyRegistry(tmp_path / "nope").list() == []


def test_load_parses_strategy(tmp_path):
    d = tmp_path / "strategies"
    _write(
        d,
        "momentum.yaml",
        "id: momentum\nname: Momentum\nintent: buy strong names\n"
        "universe: [AAPL, MSFT]\nsignals_needed: [price, market_cap]\n"
        "risk_overrides:\n  max_position_pct: 15\n",
    )
    s = StrategyRegistry(d).load("momentum")
    assert s.name == "Momentum"
    assert s.universe == ["AAPL", "MSFT"]
    assert s.signals_needed == {Signal.PRICE, Signal.MARKET_CAP}
    assert s.risk_overrides == {"max_position_pct": 15}


def test_load_missing_raises(tmp_path):
    with pytest.raises(StrategyNotFoundError):
        StrategyRegistry(tmp_path / "strategies").load("ghost")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_strategy_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rh_wizard.strategies'`.

- [ ] **Step 3: Write minimal implementation**

Add to `src/rh_wizard/config/paths.py` (after `db_path`):

```python
def strategies_dir() -> Path:
    return home_dir() / "strategies"
```

```python
# src/rh_wizard/strategies/__init__.py
```

```python
# src/rh_wizard/strategies/registry.py
"""Load strategies from YAML files in a directory (spec §5).

Each ``<id>.yaml`` holds one ``Strategy``. ``list()`` returns the available ids; ``load(id)``
parses ``<id>.yaml``. Code-module strategies are a later extension point.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from rh_wizard.models.strategy import Strategy


class StrategyNotFoundError(Exception):
    pass


class StrategyRegistry:
    def __init__(self, directory: Path) -> None:
        self._dir = Path(directory)

    def list(self) -> list[str]:
        if not self._dir.is_dir():
            return []
        return sorted(p.stem for p in self._dir.glob("*.yaml"))

    def load(self, strategy_id: str) -> Strategy:
        path = self._dir / f"{strategy_id}.yaml"
        if not path.is_file():
            raise StrategyNotFoundError(
                f"Strategy '{strategy_id}' not found in {self._dir}"
            )
        data = yaml.safe_load(path.read_text()) or {}
        return Strategy(**data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_strategy_registry.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/strategies/__init__.py src/rh_wizard/strategies/registry.py src/rh_wizard/config/paths.py tests/unit/test_strategy_registry.py
git commit -m "feat: add StrategyRegistry (YAML) and paths.strategies_dir"
```

---

### Task 4: `Researcher` interface + `StubResearcher`

The research seam (spec §5) and its deterministic stub: flag the resolved universe symbols as candidates.

**Files:**
- Create: `src/rh_wizard/research/__init__.py` (empty)
- Create: `src/rh_wizard/research/base.py`
- Create: `src/rh_wizard/research/stub.py`
- Test: `tests/unit/test_research_stub.py`

**Interfaces:**
- Consumes: `Strategy` (Task 1), `ResearchReport`/`Candidate` (Task 2), `MarketContext` (`rh_wizard.models.market`), `PortfolioState` (`rh_wizard.models.portfolio`).
- Produces:
  - `Researcher` (`@runtime_checkable` Protocol): `research(self, strategy: Strategy, market: MarketContext, portfolio: PortfolioState) -> ResearchReport`.
  - `StubResearcher` implementing it.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_research_stub.py
from decimal import Decimal

from rh_wizard.models.market import MarketContext, SymbolData
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.strategy import Strategy
from rh_wizard.research.base import Researcher
from rh_wizard.research.stub import StubResearcher


def _portfolio():
    return PortfolioState(account_number="A", positions=[], cash=Decimal("10000"),
                          buying_power=Decimal("10000"))


def test_stub_is_a_researcher():
    assert isinstance(StubResearcher(), Researcher)


def test_stub_flags_resolved_universe_symbols():
    strategy = Strategy(id="m", name="M", universe=["AAPL", "ZZZZ"])
    market = MarketContext(symbols={"AAPL": SymbolData(symbol="AAPL", price="190")})
    report = StubResearcher().research(strategy, market, _portfolio())
    # only AAPL resolved in the market context -> only AAPL is a candidate
    assert [c.symbol for c in report.candidates] == ["AAPL"]
    assert report.summary  # non-empty stub summary


def test_stub_empty_when_nothing_resolved():
    strategy = Strategy(id="m", name="M", universe=["AAPL"])
    report = StubResearcher().research(strategy, MarketContext(), _portfolio())
    assert report.candidates == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_research_stub.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rh_wizard.research'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/rh_wizard/research/__init__.py
```

```python
# src/rh_wizard/research/base.py
"""The research seam (spec §5). A Researcher investigates a strategy's universe against the
resolved MarketContext and returns a structured ResearchReport. It cannot place orders. The
Phase 4b LLM agent and the Phase 4a deterministic stub both implement this Protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rh_wizard.models.market import MarketContext
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.research import ResearchReport
from rh_wizard.models.strategy import Strategy


@runtime_checkable
class Researcher(Protocol):
    def research(
        self, strategy: Strategy, market: MarketContext, portfolio: PortfolioState
    ) -> ResearchReport: ...
```

```python
# src/rh_wizard/research/stub.py
"""Deterministic stand-in for the Phase 4b research agent. Flags every universe symbol that
actually resolved in the MarketContext as a neutral candidate — enough to drive the cycle
end-to-end offline. NOT a research strategy."""

from __future__ import annotations

from rh_wizard.models.market import MarketContext
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.research import Candidate, ResearchReport
from rh_wizard.models.strategy import Strategy


class StubResearcher:
    def research(
        self, strategy: Strategy, market: MarketContext, portfolio: PortfolioState
    ) -> ResearchReport:
        candidates = [
            Candidate(symbol=sym, thesis="(stub) candidate from strategy universe")
            for sym in strategy.universe
            if sym in market.symbols
        ]
        return ResearchReport(
            candidates=candidates,
            summary=f"(stub) {len(candidates)} candidate(s) from strategy '{strategy.id}'",
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_research_stub.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/research/ tests/unit/test_research_stub.py
git commit -m "feat: add Researcher seam and StubResearcher"
```

---

### Task 5: `Planner` interface + `StubPlanner`

The plan seam (spec §5) and its deterministic stub: a 1-share limit buy (at the current price) of each candidate not already held.

**Files:**
- Create: `src/rh_wizard/planning/__init__.py` (empty)
- Create: `src/rh_wizard/planning/base.py`
- Create: `src/rh_wizard/planning/stub.py`
- Test: `tests/unit/test_planning_stub.py`

**Interfaces:**
- Consumes: `Strategy` (Task 1), `ResearchReport` (Task 2), `MarketContext` (`rh_wizard.models.market`), `PortfolioState`/`Position` (`rh_wizard.models.portfolio`), `TradePlan`/`TradeIntent` (`rh_wizard.models.plan`).
- Produces:
  - `Planner` (`@runtime_checkable` Protocol): `plan(self, strategy: Strategy, report: ResearchReport, market: MarketContext, portfolio: PortfolioState) -> TradePlan`.
  - `StubPlanner` implementing it.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_planning_stub.py
from decimal import Decimal

from rh_wizard.models.market import MarketContext, SymbolData
from rh_wizard.models.portfolio import PortfolioState, Position
from rh_wizard.models.research import Candidate, ResearchReport
from rh_wizard.models.strategy import Strategy
from rh_wizard.planning.base import Planner
from rh_wizard.planning.stub import StubPlanner


def _market():
    return MarketContext(
        symbols={
            "AAPL": SymbolData(symbol="AAPL", price="190"),
            "MSFT": SymbolData(symbol="MSFT", price="400"),
        }
    )


def _portfolio(positions=None):
    return PortfolioState(account_number="A", positions=positions or [],
                          cash=Decimal("10000"), buying_power=Decimal("10000"))


def _report(*symbols):
    return ResearchReport(candidates=[Candidate(symbol=s) for s in symbols])


def test_stub_is_a_planner():
    assert isinstance(StubPlanner(), Planner)


def test_stub_proposes_one_share_buy_per_candidate_at_market():
    plan = StubPlanner().plan(
        Strategy(id="m", name="M"), _report("AAPL", "MSFT"), _market(), _portfolio()
    )
    by_symbol = {i.symbol: i for i in plan.intents}
    assert set(by_symbol) == {"AAPL", "MSFT"}
    assert by_symbol["AAPL"].side == "buy"
    assert by_symbol["AAPL"].quantity == Decimal("1")
    assert by_symbol["AAPL"].limit_price == Decimal("190")  # at current market price


def test_stub_skips_already_held_symbols():
    held = Position(symbol="AAPL", quantity="5", average_cost="100", cost_basis="500")
    plan = StubPlanner().plan(
        Strategy(id="m", name="M"), _report("AAPL", "MSFT"), _market(), _portfolio([held])
    )
    assert [i.symbol for i in plan.intents] == ["MSFT"]


def test_stub_skips_candidates_without_a_price():
    market = MarketContext(symbols={"AAPL": SymbolData(symbol="AAPL")})  # price is None
    plan = StubPlanner().plan(Strategy(id="m", name="M"), _report("AAPL"), market, _portfolio())
    assert plan.intents == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_planning_stub.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rh_wizard.planning'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/rh_wizard/planning/__init__.py
```

```python
# src/rh_wizard/planning/base.py
"""The plan seam (spec §5). A Planner turns a ResearchReport (+ portfolio + market) into a
proposed TradePlan that must still survive the risk engine. The Phase 4b LLM generator and
the Phase 4a deterministic stub both implement this Protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rh_wizard.models.market import MarketContext
from rh_wizard.models.plan import TradePlan
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.research import ResearchReport
from rh_wizard.models.strategy import Strategy


@runtime_checkable
class Planner(Protocol):
    def plan(
        self,
        strategy: Strategy,
        report: ResearchReport,
        market: MarketContext,
        portfolio: PortfolioState,
    ) -> TradePlan: ...
```

```python
# src/rh_wizard/planning/stub.py
"""Deterministic stand-in for the Phase 4b plan generator. Proposes a 1-share limit buy (at
the current market price, so it's within any slippage band) of each candidate not already
held and with a known price. Exercises the full risk/render/journal pipeline; NOT a trading
strategy."""

from __future__ import annotations

from decimal import Decimal

from rh_wizard.models.market import MarketContext
from rh_wizard.models.plan import TradeIntent, TradePlan
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.research import ResearchReport
from rh_wizard.models.strategy import Strategy


class StubPlanner:
    def plan(
        self,
        strategy: Strategy,
        report: ResearchReport,
        market: MarketContext,
        portfolio: PortfolioState,
    ) -> TradePlan:
        held = {p.symbol for p in portfolio.positions}
        intents: list[TradeIntent] = []
        for candidate in report.candidates:
            if candidate.symbol in held:
                continue
            data = market.symbols.get(candidate.symbol)
            if data is None or data.price is None:
                continue
            intents.append(
                TradeIntent(
                    side="buy",
                    symbol=candidate.symbol,
                    quantity=Decimal("1"),
                    limit_price=data.price,
                    rationale="(stub) 1-share probe buy",
                )
            )
        return TradePlan(intents=intents, rationale="(stub) deterministic plan")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_planning_stub.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/planning/ tests/unit/test_planning_stub.py
git commit -m "feat: add Planner seam and StubPlanner"
```

---

### Task 6: Journal — record runs and plans

Extend `SqliteJournal` with a `runs` table and a `plan_intents` table (the auditable decision record), plus writers and a reader. The existing `trades` table/methods are untouched.

**Files:**
- Modify: `src/rh_wizard/memory/journal.py`
- Test: `tests/unit/test_journal_runs.py`

**Interfaces:**
- Consumes: `CycleRun` (Task 2), `VettedPlan`/`TradeIntent`/`RejectedIntent` (`rh_wizard.models.plan`).
- Produces (on `SqliteJournal`):
  - `record_run(self, run: CycleRun) -> None` (upsert by `run_id`).
  - `record_plan(self, run_id: str, vetted: VettedPlan) -> None` (replaces any existing rows for `run_id`; writes approved then rejected intents).
  - `recent_runs(self, limit: int = 50) -> list[CycleRun]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_journal_runs.py
from decimal import Decimal

from rh_wizard.memory.journal import SqliteJournal
from rh_wizard.models.cycle import CycleRun
from rh_wizard.models.plan import RejectedIntent, TradeIntent, VettedPlan


def _run(run_id="r1", status="completed"):
    return CycleRun(run_id=run_id, strategy_id="m", mode="dryrun",
                    started_at="2026-06-23T00:00:00", finished_at="2026-06-23T00:00:01",
                    status=status)


def test_record_and_read_run():
    with SqliteJournal(":memory:") as j:
        j.record_run(_run())
        runs = j.recent_runs()
    assert [r.run_id for r in runs] == ["r1"]
    assert runs[0].status == "completed"


def test_record_run_upserts():
    with SqliteJournal(":memory:") as j:
        j.record_run(_run(status="completed"))
        j.record_run(_run(status="aborted"))  # same run_id
        runs = j.recent_runs()
    assert len(runs) == 1
    assert runs[0].status == "aborted"


def test_record_plan_persists_approved_and_rejected():
    vetted = VettedPlan(
        approved=[TradeIntent(side="buy", symbol="AAPL", quantity="1", limit_price="190")],
        rejected=[RejectedIntent(
            intent=TradeIntent(side="buy", symbol="NVDA", quantity="1", limit_price="1000"),
            reason="would exceed max position",
        )],
    )
    with SqliteJournal(":memory:") as j:
        j.record_run(_run())
        j.record_plan("r1", vetted)
        rows = j.plan_intents("r1")
    buckets = {(row["symbol"], row["bucket"]): row for row in rows}
    assert ("AAPL", "approved") in buckets
    assert ("NVDA", "rejected") in buckets
    assert buckets[("NVDA", "rejected")]["reason"] == "would exceed max position"
    assert buckets[("AAPL", "approved")]["limit_price"] == "190"


def test_record_plan_replaces_prior_rows_for_run():
    with SqliteJournal(":memory:") as j:
        j.record_run(_run())
        j.record_plan("r1", VettedPlan(
            approved=[TradeIntent(side="buy", symbol="AAPL", quantity="1", limit_price="190")]))
        j.record_plan("r1", VettedPlan(
            approved=[TradeIntent(side="buy", symbol="MSFT", quantity="1", limit_price="400")]))
        rows = j.plan_intents("r1")
    assert [r["symbol"] for r in rows] == ["MSFT"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_journal_runs.py -v`
Expected: FAIL with `AttributeError: 'SqliteJournal' object has no attribute 'record_run'`.

- [ ] **Step 3: Write minimal implementation**

In `src/rh_wizard/memory/journal.py`, extend `_SCHEMA` (append the two tables to the existing schema string) and add the methods. Replace the `_SCHEMA` assignment with:

```python
_SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    order_id   TEXT PRIMARY KEY,
    symbol     TEXT NOT NULL,
    side       TEXT NOT NULL,
    quantity   TEXT NOT NULL,
    price      TEXT,
    state      TEXT NOT NULL,
    created_at TEXT NOT NULL,
    source     TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    mode        TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    status      TEXT NOT NULL,
    note        TEXT
);
CREATE TABLE IF NOT EXISTS plan_intents (
    run_id      TEXT NOT NULL,
    seq         INTEGER NOT NULL,
    bucket      TEXT NOT NULL,
    side        TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    quantity    TEXT,
    amount      TEXT,
    limit_price TEXT,
    rationale   TEXT,
    reason      TEXT,
    PRIMARY KEY (run_id, seq)
);
"""
```

Add the import at the top (next to the `TradeRecord` import):

```python
from rh_wizard.models.cycle import CycleRun
from rh_wizard.models.plan import RejectedIntent, TradeIntent, VettedPlan
```

Add these methods to `SqliteJournal` (after `recent_trades`):

```python
    def record_run(self, run: CycleRun) -> None:
        self._conn.execute(
            """
            INSERT INTO runs (run_id, strategy_id, mode, started_at, finished_at, status, note)
            VALUES (:run_id, :strategy_id, :mode, :started_at, :finished_at, :status, :note)
            ON CONFLICT(run_id) DO UPDATE SET
                finished_at = excluded.finished_at,
                status = excluded.status,
                note = excluded.note;
            """,
            {
                "run_id": run.run_id,
                "strategy_id": run.strategy_id,
                "mode": run.mode,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
                "status": run.status,
                "note": run.note,
            },
        )
        self._conn.commit()

    def record_plan(self, run_id: str, vetted: VettedPlan) -> None:
        self._conn.execute("DELETE FROM plan_intents WHERE run_id = ?", (run_id,))
        rows = []
        seq = 0
        for intent in vetted.approved:
            rows.append(_intent_row(run_id, seq, "approved", intent, None))
            seq += 1
        for rejected in vetted.rejected:
            rows.append(_intent_row(run_id, seq, "rejected", rejected.intent, rejected.reason))
            seq += 1
        if rows:
            self._conn.executemany(
                """
                INSERT INTO plan_intents
                    (run_id, seq, bucket, side, symbol, quantity, amount, limit_price,
                     rationale, reason)
                VALUES
                    (:run_id, :seq, :bucket, :side, :symbol, :quantity, :amount, :limit_price,
                     :rationale, :reason);
                """,
                rows,
            )
        self._conn.commit()

    def recent_runs(self, limit: int = 50) -> list[CycleRun]:
        cur = self._conn.execute(
            "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
        )
        return [
            CycleRun(
                run_id=row["run_id"],
                strategy_id=row["strategy_id"],
                mode=row["mode"],
                started_at=row["started_at"],
                finished_at=row["finished_at"],
                status=row["status"],
                note=row["note"] or "",
            )
            for row in cur.fetchall()
        ]

    def plan_intents(self, run_id: str) -> list[dict]:
        cur = self._conn.execute(
            "SELECT * FROM plan_intents WHERE run_id = ? ORDER BY seq", (run_id,)
        )
        return [dict(row) for row in cur.fetchall()]
```

Add this module-level helper (after `_row_to_trade`):

```python
def _intent_row(
    run_id: str, seq: int, bucket: str, intent: TradeIntent, reason: str | None
) -> dict:
    return {
        "run_id": run_id,
        "seq": seq,
        "bucket": bucket,
        "side": intent.side,
        "symbol": intent.symbol,
        "quantity": None if intent.quantity is None else str(intent.quantity),
        "amount": None if intent.amount is None else str(intent.amount),
        "limit_price": None if intent.limit_price is None else str(intent.limit_price),
        "rationale": intent.rationale,
        "reason": reason,
    }
```

> Note: `RejectedIntent` and `TradeIntent` are imported for use in `_intent_row`/`record_plan`; if ruff flags `RejectedIntent` as unused (it is only a type referenced in the loop, not constructed), remove it from the import — keep only what the code constructs/annotates.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_journal_runs.py -v`
Expected: PASS (4 tests). Also run `uv run pytest tests/unit/test_journal.py tests/unit/test_sync.py -v` to confirm the existing trades behavior still passes.

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/memory/journal.py tests/unit/test_journal_runs.py
git commit -m "feat: journal records cycle runs and vetted plan intents"
```

---

### Task 7: Cycle orchestrator — `run_cycle`

The deterministic skeleton (spec §8). Reconcile → resolve → research → plan → vet → journal, in DryRun mode, returning a `CycleResult` bundle for rendering. Aborts cleanly if reconciliation fails.

**Files:**
- Create: `src/rh_wizard/core/__init__.py` (empty)
- Create: `src/rh_wizard/core/cycle.py`
- Test: `tests/unit/test_cycle.py`

**Interfaces:**
- Consumes: `Strategy` (T1), `CycleMode`/`CycleRun` (T2), `ResearchReport` (T2), `Researcher` (T4), `Planner` (T5), `SqliteJournal` (T6), `SignalResolver` (`rh_wizard.data.resolver`), `reconcile`/`enrich_with_quotes` (`rh_wizard.memory.portfolio`), `build_effective_policy` (`rh_wizard.risk.policy`), `vet` (`rh_wizard.risk.engine`), `RISK_SIGNALS` (`rh_wizard.models.signals`), `Settings` (`rh_wizard.config.settings`), `MarketContext` (`rh_wizard.models.market`), `PortfolioState` (`rh_wizard.models.portfolio`), `TradePlan`/`VettedPlan` (`rh_wizard.models.plan`).
- Produces (in `core/cycle.py`):
  - `CycleDeps` (dataclass): `broker`, `settings: Settings`, `resolver: SignalResolver`, `researcher: Researcher`, `planner: Planner`, `journal: SqliteJournal`.
  - `CycleResult` (dataclass): `run: CycleRun`, `portfolio: PortfolioState | None = None`, `market: MarketContext | None = None`, `report: ResearchReport | None = None`, `plan: TradePlan | None = None`, `vetted: VettedPlan | None = None`.
  - `run_cycle(strategy: Strategy, deps: CycleDeps, mode: CycleMode = CycleMode.DRY_RUN) -> CycleResult`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_cycle.py
from decimal import Decimal

from rh_wizard.config.settings import Settings
from rh_wizard.core.cycle import CycleDeps, run_cycle
from rh_wizard.data.resolver import SignalResolver
from rh_wizard.memory.journal import SqliteJournal
from rh_wizard.models.market import SymbolData
from rh_wizard.models.signals import RISK_SIGNALS, Signal
from rh_wizard.models.strategy import Strategy
from rh_wizard.planning.stub import StubPlanner
from rh_wizard.research.stub import StubResearcher


class FakeBroker:
    def __init__(self, raise_accounts=False):
        self._raise = raise_accounts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_accounts(self):
        if self._raise:
            raise RuntimeError("broker down")
        return [{"account_number": "ACC1", "agentic_allowed": True}]

    def get_equity_positions(self, account_number):
        return []

    def get_portfolio(self, account_number):
        return {"data": {"cash": "10000", "buying_power": "10000"}}

    def get_equity_quotes(self, symbols):
        return [{"symbol": s, "last_trade_price": "100"} for s in symbols]


class FakeDataSource:
    name = "fake"

    def provides(self):
        return set(RISK_SIGNALS) | {Signal.PRICE}

    def fetch(self, symbols, signals):
        return {
            s: SymbolData(symbol=s, price="100", average_volume="50000000",
                          market_cap="3000000000000")
            for s in symbols
        }


def _deps(journal, broker=None):
    return CycleDeps(
        broker=broker or FakeBroker(),
        settings=Settings(),
        resolver=SignalResolver([FakeDataSource()]),
        researcher=StubResearcher(),
        planner=StubPlanner(),
        journal=journal,
    )


def test_cycle_completes_and_vets_a_plan():
    strategy = Strategy(id="m", name="M", universe=["AAPL"], signals_needed={Signal.PRICE})
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal)
        with deps.broker:
            result = run_cycle(strategy, deps)
        assert result.run.status == "completed"
        assert result.run.finished_at is not None
        # 1-share AAPL buy at $100 is within all guardrails -> approved
        assert [i.symbol for i in result.vetted.approved] == ["AAPL"]
        # the run + plan were journaled
        assert journal.recent_runs()[0].run_id == result.run.run_id
        symbols = {row["symbol"] for row in journal.plan_intents(result.run.run_id)}
        assert symbols == {"AAPL"}


def test_cycle_aborts_when_reconcile_fails():
    strategy = Strategy(id="m", name="M", universe=["AAPL"])
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal, broker=FakeBroker(raise_accounts=True))
        with deps.broker:
            result = run_cycle(strategy, deps)
        assert result.run.status == "aborted"
        assert "broker down" in result.run.note
        assert result.vetted is None
        # the aborted run is still journaled
        assert journal.recent_runs()[0].status == "aborted"


def test_cycle_includes_held_symbols_in_universe():
    # AAPL already held -> stub planner won't buy it; universe still resolves it.
    strategy = Strategy(id="m", name="M", universe=["MSFT"], signals_needed={Signal.PRICE})

    class HeldBroker(FakeBroker):
        def get_equity_positions(self, account_number):
            return [{"symbol": "AAPL", "quantity": "5", "average_cost": "90"}]

    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal, broker=HeldBroker())
        with deps.broker:
            result = run_cycle(strategy, deps)
        # MSFT (new) approved; AAPL held so not bought
        assert [i.symbol for i in result.vetted.approved] == ["MSFT"]
        assert "AAPL" in result.market.symbols  # held symbol was resolved
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cycle.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rh_wizard.core'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/rh_wizard/core/__init__.py
```

```python
# src/rh_wizard/core/cycle.py
"""The deterministic trading cycle (spec §8) — Phase 4a, DryRun only.

``run_cycle`` runs the fixed pipeline in order: reconcile (Phase 1) -> resolve signals
(Phase 3) -> research -> plan (stubs in 4a) -> risk vet (Phase 2) -> journal. It places no
orders (no executor exists yet — Phase 5) and never trusts local state for holdings. The
caller opens the broker context. Reconciliation failure aborts the cycle cleanly (spec §13).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from rh_wizard.config.settings import Settings
from rh_wizard.data.resolver import SignalResolver
from rh_wizard.memory.journal import SqliteJournal
from rh_wizard.memory.portfolio import enrich_with_quotes, reconcile
from rh_wizard.models.cycle import CycleMode, CycleRun
from rh_wizard.models.market import MarketContext
from rh_wizard.models.plan import TradePlan, VettedPlan
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.research import ResearchReport
from rh_wizard.models.signals import RISK_SIGNALS
from rh_wizard.models.strategy import Strategy
from rh_wizard.planning.base import Planner
from rh_wizard.research.base import Researcher
from rh_wizard.risk.engine import vet
from rh_wizard.risk.policy import build_effective_policy


@dataclass
class CycleDeps:
    broker: object
    settings: Settings
    resolver: SignalResolver
    researcher: Researcher
    planner: Planner
    journal: SqliteJournal


@dataclass
class CycleResult:
    run: CycleRun
    portfolio: PortfolioState | None = None
    market: MarketContext | None = None
    report: ResearchReport | None = None
    plan: TradePlan | None = None
    vetted: VettedPlan | None = None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def run_cycle(
    strategy: Strategy, deps: CycleDeps, mode: CycleMode = CycleMode.DRY_RUN
) -> CycleResult:
    run = CycleRun(
        run_id=uuid.uuid4().hex,
        strategy_id=strategy.id,
        mode=mode.value,
        started_at=_now(),
    )

    # Stage 3 (RECONCILE) — broker is ground truth; failure aborts (spec §13).
    try:
        portfolio = enrich_with_quotes(reconcile(deps.broker, deps.settings), deps.broker)
    except Exception as exc:
        run = run.model_copy(
            update={"status": "aborted", "finished_at": _now(), "note": f"reconcile failed: {exc}"}
        )
        deps.journal.record_run(run)
        return CycleResult(run=run)

    # Stage 5 (RESOLVE SIGNALS) over the strategy universe + current holdings.
    universe = sorted(set(strategy.universe) | {p.symbol for p in portfolio.positions})
    needed = set(strategy.signals_needed) | set(RISK_SIGNALS)
    market = deps.resolver.resolve(universe, needed)

    # Stages 6-7 (RESEARCH, PLAN) — stubs in Phase 4a.
    report = deps.researcher.research(strategy, market, portfolio)
    plan = deps.planner.plan(strategy, report, market, portfolio)

    # Stage 8 (RISK ENGINE) — pure, deterministic (Phase 2).
    policy = build_effective_policy(
        deps.settings.risk, deps.settings.risk_ceiling, strategy.risk_overrides
    )
    vetted = vet(plan, policy, portfolio, market.to_symbol_risk())

    # Stage 9: DryRun — no execution (Phase 5 adds the executor). Stage 11: JOURNAL.
    run = run.model_copy(update={"status": "completed", "finished_at": _now()})
    deps.journal.record_run(run)
    deps.journal.record_plan(run.run_id, vetted)

    return CycleResult(
        run=run, portfolio=portfolio, market=market, report=report, plan=plan, vetted=vetted
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_cycle.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/core/ tests/unit/test_cycle.py
git commit -m "feat: add deterministic DryRun cycle orchestrator (run_cycle)"
```

---

### Task 8: DryRun rendering — `render_cycle_result`

Render a `CycleResult` for the terminal: run header, portfolio summary, research summary, the vetted plan (approved + rejected with reasons), and the DryRun footer.

**Files:**
- Modify: `src/rh_wizard/cli/render.py`
- Test: `tests/unit/test_render_cycle.py`

**Interfaces:**
- Consumes: `CycleResult` (Task 7), existing `fmt_money`/`fmt_num`/`render_to_str` (`cli/render.py`).
- Produces: `render_cycle_result(result) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_render_cycle.py
from decimal import Decimal

from rh_wizard.cli.render import render_cycle_result
from rh_wizard.core.cycle import CycleResult
from rh_wizard.models.cycle import CycleRun
from rh_wizard.models.plan import RejectedIntent, TradeIntent, VettedPlan
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.research import ResearchReport


def _run(status="completed", note=""):
    return CycleRun(run_id="abc123", strategy_id="momentum", mode="dryrun",
                    started_at="2026-06-23T00:00:00", finished_at="2026-06-23T00:00:01",
                    status=status, note=note)


def test_render_completed_run_shows_plan_and_dryrun_footer():
    result = CycleResult(
        run=_run(),
        portfolio=PortfolioState(account_number="ACC1", positions=[], cash=Decimal("10000"),
                                 buying_power=Decimal("10000"), total_value=Decimal("10000")),
        report=ResearchReport(summary="(stub) 1 candidate"),
        vetted=VettedPlan(
            approved=[TradeIntent(side="buy", symbol="AAPL", quantity="1", limit_price="190")],
            rejected=[RejectedIntent(
                intent=TradeIntent(side="buy", symbol="NVDA", quantity="1", limit_price="1000"),
                reason="would exceed max position")],
        ),
    )
    out = render_cycle_result(result)
    assert "momentum" in out
    assert "abc123" in out
    assert "AAPL" in out          # approved intent
    assert "NVDA" in out          # rejected intent
    assert "would exceed max position" in out
    assert "DryRun" in out        # footer
    assert "no orders" in out.lower()


def test_render_aborted_run_shows_reason():
    out = render_cycle_result(CycleResult(run=_run(status="aborted", note="reconcile failed: x")))
    assert "ABORTED" in out.upper()
    assert "reconcile failed: x" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_render_cycle.py -v`
Expected: FAIL with `ImportError: cannot import name 'render_cycle_result'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/rh_wizard/cli/render.py`:

```python
def render_cycle_result(result) -> str:
    """Render a CycleResult (run header + portfolio + research + vetted plan + DryRun footer)."""
    from rich.table import Table

    run = result.run
    header = f"Run {run.run_id} — strategy '{run.strategy_id}' — mode {run.mode} — {run.status}"
    if run.status != "completed":
        return f"{header}\nABORTED: {run.note}\n"

    lines = [header]
    if result.portfolio is not None:
        p = result.portfolio
        lines.append(
            f"Cash: {fmt_money(p.cash)}   Total value: {fmt_money(p.total_value)}"
        )
    if result.report is not None and result.report.summary:
        lines.append(f"Research: {result.report.summary}")

    vetted = result.vetted
    if vetted is not None and vetted.approved:
        table = Table(title="Proposed trades (DryRun — approved)")
        table.add_column("Side")
        table.add_column("Symbol")
        table.add_column("Qty", justify="right")
        table.add_column("Limit", justify="right")
        table.add_column("Rationale")
        for i in vetted.approved:
            table.add_row(i.side, i.symbol, fmt_num(i.quantity), fmt_money(i.limit_price),
                          i.rationale or "-")
        lines.append(render_to_str(table).rstrip("\n"))
    else:
        lines.append("No trades proposed.")

    if vetted is not None and vetted.rejected:
        lines.append("Rejected:")
        for r in vetted.rejected:
            lines.append(f"  {r.intent.side} {r.intent.symbol}: {r.reason}")

    lines.append("DryRun — no orders placed.")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_render_cycle.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/cli/render.py tests/unit/test_render_cycle.py
git commit -m "feat: add render_cycle_result (DryRun plan rendering)"
```

---

### Task 9: CLI — `wizard run` + `wizard strategies`

Wire the cycle into the CLI (read-only, DryRun) and list available strategies. Commit an example strategy file.

**Files:**
- Create: `src/rh_wizard/cli/run.py`
- Modify: `src/rh_wizard/cli/app.py`
- Create: `strategies.example/sample-momentum.yaml`
- Test: `tests/unit/test_cli_run.py`

**Interfaces:**
- Consumes: `auth._build_broker` (`cli/auth.py`), `load_settings` (`config/settings.py`), `paths` (`config/paths.py`), `StrategyRegistry`/`StrategyNotFoundError` (T3), `RobinhoodDataSource` (`data/robinhood.py`), `SignalResolver` (`data/resolver.py`), `StubResearcher` (T4), `StubPlanner` (T5), `SqliteJournal` (T6), `CycleDeps`/`run_cycle` (T7), `CycleMode` (T2), `render_cycle_result` (T8).
- Produces:
  - `cli/run.py`: `run_strategy(strategy_id: str) -> None`, `list_strategies() -> None`.
  - `cli/app.py`: `run` and `strategies` commands.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_cli_run.py
from typer.testing import CliRunner

from rh_wizard.cli import auth
from rh_wizard.cli.app import app

runner = CliRunner()


class FakeBroker:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_accounts(self):
        return [{"account_number": "ACC1", "agentic_allowed": True}]

    def get_equity_positions(self, account_number):
        return []

    def get_portfolio(self, account_number):
        return {"data": {"cash": "10000", "buying_power": "10000"}}

    def get_equity_quotes(self, symbols):
        return [{"symbol": s, "last_trade_price": "100"} for s in symbols]

    def get_equity_fundamentals(self, symbols):
        return [
            {"symbol": s, "average_volume": "50000000", "market_cap": "3000000000000"}
            for s in symbols
        ]


def _write_strategy(home):
    d = home / "strategies"
    d.mkdir(parents=True, exist_ok=True)
    (d / "demo.yaml").write_text(
        "id: demo\nname: Demo\nuniverse: [AAPL]\nsignals_needed: [price]\n"
    )


def test_strategies_lists_available(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))
    _write_strategy(tmp_path)
    result = runner.invoke(app, ["strategies"])
    assert result.exit_code == 0
    assert "demo" in result.output


def test_run_executes_dryrun_cycle_and_renders(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))
    _write_strategy(tmp_path)
    monkeypatch.setattr(auth, "_build_broker", lambda settings: FakeBroker())
    result = runner.invoke(app, ["run", "demo"])
    assert result.exit_code == 0
    assert "AAPL" in result.output          # 1-share probe buy proposed
    assert "DryRun" in result.output
    assert "no orders" in result.output.lower()


def test_run_unknown_strategy_errors(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))
    monkeypatch.setattr(auth, "_build_broker", lambda settings: FakeBroker())
    result = runner.invoke(app, ["run", "ghost"])
    assert result.exit_code != 0
    assert "ghost" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli_run.py -v`
Expected: FAIL — the `run`/`strategies` commands are not registered (Typer exits non-zero / "No such command").

- [ ] **Step 3: Write minimal implementation**

```python
# src/rh_wizard/cli/run.py
"""`wizard run <strategy>` (DryRun cycle) and `wizard strategies` (list)."""

from __future__ import annotations

import typer

from rh_wizard.cli import auth
from rh_wizard.cli.render import render_cycle_result
from rh_wizard.config import paths
from rh_wizard.config.settings import load_settings
from rh_wizard.core.cycle import CycleDeps, run_cycle
from rh_wizard.data.resolver import SignalResolver
from rh_wizard.data.robinhood import RobinhoodDataSource
from rh_wizard.memory.journal import SqliteJournal
from rh_wizard.models.cycle import CycleMode
from rh_wizard.planning.stub import StubPlanner
from rh_wizard.research.stub import StubResearcher
from rh_wizard.strategies.registry import StrategyNotFoundError, StrategyRegistry


def list_strategies() -> None:
    registry = StrategyRegistry(paths.strategies_dir())
    ids = registry.list()
    if not ids:
        typer.echo(f"No strategies found in {paths.strategies_dir()}.")
        return
    for sid in ids:
        typer.echo(sid)


def run_strategy(strategy_id: str) -> None:
    paths.ensure_home()
    settings = load_settings()
    registry = StrategyRegistry(paths.strategies_dir())
    try:
        strategy = registry.load(strategy_id)
    except StrategyNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc

    broker = auth._build_broker(settings)
    resolver = SignalResolver([RobinhoodDataSource(broker)])
    with broker, SqliteJournal(paths.db_path()) as journal:
        deps = CycleDeps(
            broker=broker,
            settings=settings,
            resolver=resolver,
            researcher=StubResearcher(),
            planner=StubPlanner(),
            journal=journal,
        )
        result = run_cycle(strategy, deps, CycleMode.DRY_RUN)
    typer.echo(render_cycle_result(result))
```

In `src/rh_wizard/cli/app.py`, add the import (with the other `cli` imports):

```python
from rh_wizard.cli.run import list_strategies, run_strategy
```

And the two commands (after the existing `data` command):

```python
@app.command()
def strategies() -> None:
    """List strategies available in ~/.rh-wizard/strategies/."""
    list_strategies()


@app.command()
def run(
    strategy_id: str = typer.Argument(..., help="Strategy id (yaml filename stem)."),  # noqa: B008
) -> None:
    """Run one DryRun cycle for STRATEGY_ID — proposes a vetted plan, places no orders."""
    run_strategy(strategy_id)
```

Create the example strategy:

```yaml
# strategies.example/sample-momentum.yaml
# Copy to ~/.rh-wizard/strategies/ and run with: wizard run sample-momentum
# In this version (Phase 4a) the research/plan brain is a deterministic stub.
id: sample-momentum
name: Sample Momentum (example)
intent: >
  Example strategy. Replace with your own thesis — e.g. "20% rare-earth-metals funds,
  20% energy, 40% AI stocks with strong fundamentals". The real research/plan LLM lands
  in Phase 4b; today the agent brain is a stub that probes each candidate with a 1-share buy.
universe: [AAPL, MSFT, NVDA]
signals_needed: [price, average_volume, market_cap]
cadence: weekly
risk_overrides:
  max_position_pct: 15
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_cli_run.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/cli/run.py src/rh_wizard/cli/app.py strategies.example/sample-momentum.yaml tests/unit/test_cli_run.py
git commit -m "feat: add wizard run (DryRun cycle) + wizard strategies commands"
```

---

### Task 10: Opt-in live `wizard run` DryRun smoke

Prove the whole cycle runs end-to-end against the real broker + real Phase 3 data with the stub brain — read-only, no orders — mirroring the prior phases' live verification.

**Files:**
- Create: `tests/integration/test_live_run.py`

**Interfaces:**
- Consumes: `auth._build_broker`, `load_settings`, `paths`, `StrategyRegistry`-less direct `Strategy`, `RobinhoodDataSource`, `SignalResolver`, `StubResearcher`, `StubPlanner`, `SqliteJournal`, `CycleDeps`/`run_cycle`, `render_cycle_result`.
- Produces: an opt-in (`RH_WIZARD_LIVE=1`) test that runs a DryRun cycle against the live account and asserts it completes.

- [ ] **Step 1: Write the live test (skipped unless `RH_WIZARD_LIVE=1`)**

```python
# tests/integration/test_live_run.py
"""Live, opt-in DryRun cycle smoke against the real Robinhood MCP (read-only — no orders).

Run explicitly (needs a cached token from `wizard auth login`):
    RH_WIZARD_LIVE=1 uv run pytest tests/integration/test_live_run.py -v -s

Runs the full deterministic cycle (reconcile -> resolve -> stub research/plan -> risk vet ->
journal) and prints the rendered DryRun result. Places NO orders.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RH_WIZARD_LIVE") != "1",
    reason="set RH_WIZARD_LIVE=1 to run the live DryRun cycle smoke",
)


def test_live_dryrun_cycle(tmp_path):
    from rh_wizard.cli import auth
    from rh_wizard.cli.render import render_cycle_result
    from rh_wizard.config.settings import load_settings
    from rh_wizard.core.cycle import CycleDeps, run_cycle
    from rh_wizard.data.resolver import SignalResolver
    from rh_wizard.data.robinhood import RobinhoodDataSource
    from rh_wizard.memory.journal import SqliteJournal
    from rh_wizard.models.signals import Signal
    from rh_wizard.models.strategy import Strategy
    from rh_wizard.planning.stub import StubPlanner
    from rh_wizard.research.stub import StubResearcher

    settings = load_settings()
    strategy = Strategy(
        id="live-smoke", name="Live Smoke", universe=["AAPL", "MSFT"],
        signals_needed={Signal.PRICE, Signal.AVERAGE_VOLUME, Signal.MARKET_CAP},
    )
    broker = auth._build_broker(settings)
    resolver = SignalResolver([RobinhoodDataSource(broker)])
    with broker, SqliteJournal(tmp_path / "wizard.db") as journal:
        deps = CycleDeps(
            broker=broker, settings=settings, resolver=resolver,
            researcher=StubResearcher(), planner=StubPlanner(), journal=journal,
        )
        result = run_cycle(strategy, deps)
        rendered = render_cycle_result(result)
        recorded = journal.recent_runs()

    print("\n" + rendered)
    assert result.run.status == "completed"
    assert result.vetted is not None
    assert recorded and recorded[0].run_id == result.run.run_id
```

- [ ] **Step 2: Verify it is collected but skipped without the flag**

Run: `uv run pytest tests/integration/test_live_run.py -v`
Expected: 1 skipped (reason: "set RH_WIZARD_LIVE=1 ...").

- [ ] **Step 3: Commit**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pytest`

```bash
git add tests/integration/test_live_run.py
git commit -m "test: add opt-in live DryRun cycle smoke (skipped by default)"
```

> The live run itself (`RH_WIZARD_LIVE=1 …`) is executed during review with the user's cached token — it is read-only (reconcile + data fetch + stub plan + render), places no orders, and confirms the whole skeleton works against the real account.

---

## Final Verification

- [ ] **Run the full suite + lint**

Run: `uv run pytest && uv run ruff check . && uv run ruff format --check .`
Expected: all green (the live test is skipped without `RH_WIZARD_LIVE=1`).

- [ ] **Open the PR**

```bash
git push -u origin phase-4a
gh pr create --title "Phase 4a: deterministic DryRun cycle (stub brain)" \
  --body "Implements the deterministic DryRun trading cycle (spec §8) wiring Phases 1-3 behind Researcher/Planner seams with a stub brain. wizard run <strategy> produces a risk-vetted plan and places no orders. LLM research/plan + NL strategy compiler land in Phase 4b."
```

---

## Self-Review (completed during planning)

**Spec coverage (§5/§7/§8 stages 1–9,11–12 / §17 Phase 4):**
- Strategy + registry (§5) → Tasks 1, 3. ✅
- Research seam + report (§5/§7) → Tasks 2, 4. ✅
- Plan generator seam (§5) → Task 5; consumes the existing `TradePlan`/`vet` (Phase 2). ✅
- Cycle orchestrator, deterministic skeleton (§8 stages 1,3,5–9,11–12) → Task 7. Stage 2 (connect broker) is the caller's `with broker:` (Task 9). Stage 4 (kill-switch) deferred to Phase 6 (decision #6). Stage 10 (execute) deferred to Phase 5 (decision #5). ✅
- DryRun mode renders + stops, no orders (§10) → Tasks 7–9; `CycleMode` seam (Task 2). ✅
- Journal records plan/decisions/run (§6) → Task 6. ✅
- CLI `run`/`strategies` (§5) → Task 9. ✅
- Fakes + offline cycle test + opt-in live (§14) → Tasks 7, 10. ✅
- Forward-compat: `Strategy.intent` stored for the thematic/discovery vision; universe is a single pluggable line. ✅

**Placeholder scan:** No TBD/TODO/"handle edge cases" — every code step shows complete code.

**Type consistency:** `Strategy`, `ResearchReport`/`Candidate`, `CycleMode`/`CycleRun` defined in Tasks 1–2 and consumed identically in 3–9; `Researcher.research(strategy, market, portfolio)` (T4) and `Planner.plan(strategy, report, market, portfolio)` (T5) match the `run_cycle` call sites (T7); `CycleDeps`/`CycleResult`/`run_cycle` (T7) match the CLI (T9), render (T8), and tests; journal `record_run`/`record_plan(run_id, vetted)`/`recent_runs`/`plan_intents` (T6) match the cycle and tests. ✅
