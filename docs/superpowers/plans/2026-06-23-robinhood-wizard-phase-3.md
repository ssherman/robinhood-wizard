# Robinhood Wizard — Phase 3 Implementation Plan (Data Layer + SignalResolver)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the **structured data layer** — a pluggable `DataSource` seam, a `RobinhoodDataSource` (quotes + fundamentals), and a `SignalResolver` that routes the signals a strategy needs into a `MarketContext`, which produces the `dict[str, SymbolRisk]` the Phase 2 risk engine already consumes (spec §17 Phase 3, §5/§6/§11).

**Architecture:** A `Signal` taxonomy names the facts a strategy can request and a source can provide. `DataSource` is a `Protocol` (`provides()` + `fetch()`); `RobinhoodDataSource` wraps the typed `BrokerClient` (gaining a new `get_equity_fundamentals`). `SignalResolver` asks each source for `provides() ∩ needed`, merges the per-symbol results into a `MarketContext`, and **always degrades and reports** — never raises. Whether the result is complete enough to trade is a cycle-level decision in Phase 4. Built and tested offline with fakes; the unconfirmed fundamentals payload shape is verified hands-on with an opt-in live test (mirroring Phase 1's live shape verification).

**Tech Stack:** Python 3.12, `pydantic` v2, `Decimal` for all money/quantities, `typer` + `rich` (CLI), `pytest`, `ruff`, `uv`. No new third-party dependencies.

## Design Decisions (review these — flag if you disagree)

These resolve ambiguities in the spec's *indicative* interfaces (§6 says signatures are "finalized during implementation") and record the scoping choices agreed during brainstorming:

1. **`DataSource` = structured/quantitative data only. Web/news is an agent capability, not a Phase 3 source.** Phase 3 builds the general `DataSource` Protocol so future **API** sources (EDGAR, AlphaVantage) slot in unchanged. `NEWS`/`SENTIMENT` exist in the `Signal` taxonomy but are *declared-not-provided* seams; the Phase 4 research agent supplies them via its own live web-search/fetch tools, not a batch source. **Nothing web is implemented in Phase 3.**
2. **The Robinhood source supplies quotes + a core fundamentals bundle.** `PRICE` (from quotes); `AVERAGE_VOLUME`, `MARKET_CAP`, `PE_RATIO`, `PB_RATIO`, `SECTOR`, `INDUSTRY`, `WEEK_52_HIGH/LOW`, `DIVIDEND_YIELD` (from fundamentals). The full `Signal` taxonomy is defined (incl. `HISTORICALS`, `EARNINGS`, `NEWS`, `SENTIMENT`) but those four are declared-not-provided seams.
3. **`SignalResolver` always degrades and reports — never raises.** A *needed* signal that no source provides is recorded in `MarketContext.unmet_signals`; a source whose `fetch` raises is recorded in `MarketContext.notes`; per-symbol missing facts are simply `None` fields in `SymbolData`. Spec §13's "abort the cycle" decision lives in the Phase 4 cycle, which inspects the `MarketContext` — not in the resolver.
4. **`MarketContext.to_symbol_risk() -> dict[str, SymbolRisk]` is the bridge to the risk engine**, closing the Phase 2 forward-seam (Phase 2 decision #1: "Phase 3's data layer will supply `market` from its `MarketContext`"). Only symbols with a non-`None` `price` become `SymbolRisk` (its `price` is mandatory); `average_volume`/`market_cap` pass through (may be `None`).
5. **`fetch` returns per-symbol typed records** — `fetch(symbols, signals) -> dict[str, SymbolData]` — merged by the resolver. (Considered & rejected: signal-keyed columns and untyped dict blobs — worse to consume and to test.)
6. **The `Signal` taxonomy + `SymbolData`/`MarketContext` live in `models/`, not `data/`.** They are the shared vocabulary both `data/` and (later) `strategies/` depend on; keeping them in `models/` makes the dependency direction `data → models` (same as `risk → models`).
7. **`get_equity_fundamentals`'s payload shape is an unresolved unknown.** The broker client does not call it yet. Parsers are written defensively (multiple candidate field names) and **confirmed live** in Task 8 via an opt-in integration test, with the confirmed field names recorded in the spec's §18 (exactly as Phase 1 did for the portfolio/quote shapes).
8. **The data layer does I/O — it is not "pure" like the risk engine.** `RobinhoodDataSource` wraps the broker; `SignalResolver` orchestrates. Both are unit-tested **offline** against fakes (`FakeBroker`, `FakeDataSource`); no LLM, and no network in any unit test. Each source is fetched at most once per `resolve()` (within-cycle dedupe); cross-cycle caching is deferred.

---

## Global Constraints

Every task implicitly includes these:

- **Python:** `requires-python = ">=3.12"`; ruff `target-version = "py312"`.
- **Lint/format:** ruff `select = ["E", "F", "I", "UP", "B"]`, `line-length = 100`. Every task ends green on `uv run ruff check .` and `uv run ruff format --check .`.
- **Tests:** `uv run pytest` (configured `addopts = "-q"`, `pythonpath = ["src"]`, `testpaths = ["tests"]`). No network/LLM/broker in any **unit** test — sources and the resolver are exercised with fakes. The single live test is opt-in behind `RH_WIZARD_LIVE=1`.
- **Money/quantities are `Decimal`.** Never `float`. Construct from strings in tests (`Decimal("190.50")`). Coerce broker numerics (strings/numbers) defensively, returning `None` on anything non-numeric.
- **Models use `pydantic.BaseModel` with `from __future__ import annotations`.** `Signal` is a `str, Enum`. Output models we construct (`SymbolData`, `MarketContext`) do **not** set `extra="forbid"` (that guard is for user-supplied input like `RiskPolicy`).
- **Dependency direction:** `data/` may import `models/` and `broker/` only — never `risk/`, `memory/`, `llm/`, or `cli/`. `models/` imports nothing from `data/`.
- **No new dependencies** and **no new config keys** — `SignalResolver` is constructed in code (the cycle in Phase 4); `Settings` is unchanged.

**Branch:** Create `phase-3` off `main`. Open a PR at the end. Tasks 1–7 are fully covered by offline unit tests; Task 8 is the opt-in live shape verification (needs a cached token from `wizard auth login`).

---

## File Structure

**New files:**
- `src/rh_wizard/models/signals.py` — `Signal` enum + `RISK_SIGNALS`.
- `src/rh_wizard/data/__init__.py` — new `data/` package (empty).
- `src/rh_wizard/data/base.py` — `DataSource` Protocol.
- `src/rh_wizard/data/robinhood.py` — `RobinhoodDataSource`.
- `src/rh_wizard/data/resolver.py` — `SignalResolver`.
- `src/rh_wizard/cli/market.py` — `run_data` (`wizard data` command).
- `tests/unit/test_models_signals.py`, `test_models_market_context.py`, `test_data_source_protocol.py`, `test_broker_fundamentals.py`, `test_robinhood_source.py`, `test_signal_resolver.py`, `test_cli_data.py`
- `tests/integration/test_live_fundamentals.py`

**Modified files:**
- `src/rh_wizard/models/market.py` — add `SymbolData`, `MarketContext`.
- `src/rh_wizard/broker/client.py` — add `get_equity_fundamentals`.
- `src/rh_wizard/cli/render.py` — add `render_market_context`.
- `src/rh_wizard/cli/app.py` — register the `data` command.
- `docs/superpowers/specs/2026-06-21-robinhood-wizard-design.md` — append confirmed fundamentals shape to §18 (Task 8, after the live run).

---

### Task 1: Signal taxonomy — `models/signals.py`

The named facts a strategy can request and a source can provide (spec §3/§11). A `str, Enum` so values are YAML/JSON-friendly and sort deterministically.

**Files:**
- Create: `src/rh_wizard/models/signals.py`
- Test: `tests/unit/test_models_signals.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Signal(str, Enum)` with members: `PRICE`, `AVERAGE_VOLUME`, `MARKET_CAP`, `PE_RATIO`, `PB_RATIO`, `SECTOR`, `INDUSTRY`, `WEEK_52_HIGH`, `WEEK_52_LOW`, `DIVIDEND_YIELD`, `HISTORICALS`, `EARNINGS`, `NEWS`, `SENTIMENT` (values are the lower-case names).
  - `RISK_SIGNALS: frozenset[Signal]` = `{PRICE, AVERAGE_VOLUME, MARKET_CAP}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_models_signals.py
from rh_wizard.models.signals import RISK_SIGNALS, Signal


def test_signal_values_are_lowercase_names():
    assert Signal.PRICE.value == "price"
    assert Signal.MARKET_CAP.value == "market_cap"
    assert Signal.WEEK_52_HIGH.value == "week_52_high"


def test_signal_is_str_enum():
    # str-Enum members compare equal to their string value (YAML/JSON friendly).
    assert Signal.SECTOR == "sector"


def test_declared_seam_signals_exist():
    # Defined but not provided in Phase 3 (NEWS/SENTIMENT come from the Phase 4 agent).
    for name in ("HISTORICALS", "EARNINGS", "NEWS", "SENTIMENT"):
        assert hasattr(Signal, name)


def test_risk_signals_are_the_symbolrisk_inputs():
    assert RISK_SIGNALS == frozenset({Signal.PRICE, Signal.AVERAGE_VOLUME, Signal.MARKET_CAP})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_models_signals.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rh_wizard.models.signals'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/rh_wizard/models/signals.py
"""The signal taxonomy (spec §3/§11): the named facts a strategy can request and a data
source can provide.

Phase 3 implements the quantitative Robinhood signals (quotes + fundamentals).
``HISTORICALS``/``EARNINGS`` and ``NEWS``/``SENTIMENT`` are declared seams — not provided
in Phase 3. NEWS/SENTIMENT are supplied by the Phase 4 research agent's own web tools
(not a batch DataSource); HISTORICALS/EARNINGS by a later Robinhood or external source.
"""

from __future__ import annotations

from enum import Enum


class Signal(str, Enum):
    # --- implemented in Phase 3 (Robinhood quotes + fundamentals) ---
    PRICE = "price"
    AVERAGE_VOLUME = "average_volume"
    MARKET_CAP = "market_cap"
    PE_RATIO = "pe_ratio"
    PB_RATIO = "pb_ratio"
    SECTOR = "sector"
    INDUSTRY = "industry"
    WEEK_52_HIGH = "week_52_high"
    WEEK_52_LOW = "week_52_low"
    DIVIDEND_YIELD = "dividend_yield"
    # --- declared seams (not provided in Phase 3) ---
    HISTORICALS = "historicals"
    EARNINGS = "earnings"
    NEWS = "news"
    SENTIMENT = "sentiment"


# The signals the risk engine's SymbolRisk requires (spec §9 liquidity floor + slippage).
RISK_SIGNALS: frozenset[Signal] = frozenset(
    {Signal.PRICE, Signal.AVERAGE_VOLUME, Signal.MARKET_CAP}
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_models_signals.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/models/signals.py tests/unit/test_models_signals.py
git commit -m "feat: add Signal taxonomy and RISK_SIGNALS"
```

---

### Task 2: `SymbolData` + `MarketContext` (+ `to_symbol_risk`)

The resolved per-symbol facts (`SymbolData`) and the assembled result (`MarketContext`), with the bridge that feeds the Phase 2 risk engine.

**Files:**
- Modify: `src/rh_wizard/models/market.py`
- Test: `tests/unit/test_models_market_context.py`

**Interfaces:**
- Consumes: `Signal` (Task 1); `SymbolRisk` (existing, `models/market.py`).
- Produces (in `models/market.py`):
  - `SymbolData(symbol: str, price: Decimal | None = None, average_volume: Decimal | None = None, market_cap: Decimal | None = None, pe_ratio: Decimal | None = None, pb_ratio: Decimal | None = None, sector: str | None = None, industry: str | None = None, week_52_high: Decimal | None = None, week_52_low: Decimal | None = None, dividend_yield: Decimal | None = None)`
  - `MarketContext(requested: list[Signal] = [], symbols: dict[str, SymbolData] = {}, unmet_signals: list[Signal] = [], notes: list[str] = [])` with `to_symbol_risk(self) -> dict[str, SymbolRisk]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_models_market_context.py
from decimal import Decimal

from rh_wizard.models.market import MarketContext, SymbolData, SymbolRisk
from rh_wizard.models.signals import Signal


def test_symbol_data_defaults_are_none():
    d = SymbolData(symbol="AAPL")
    assert d.price is None
    assert d.market_cap is None
    assert d.sector is None


def test_symbol_data_coerces_decimals():
    d = SymbolData(symbol="AAPL", price="190.50", market_cap="3.0E12")
    assert d.price == Decimal("190.50")
    assert d.market_cap == Decimal("3.0E12")


def test_market_context_defaults_empty():
    ctx = MarketContext()
    assert ctx.symbols == {}
    assert ctx.requested == []
    assert ctx.unmet_signals == []
    assert ctx.notes == []


def test_to_symbol_risk_includes_only_priced_symbols():
    ctx = MarketContext(
        symbols={
            "AAPL": SymbolData(symbol="AAPL", price="190", average_volume="50000000",
                               market_cap="3.0E12"),
            "ZZZZ": SymbolData(symbol="ZZZZ"),  # no price -> excluded
        }
    )
    risk = ctx.to_symbol_risk()
    assert set(risk) == {"AAPL"}
    assert isinstance(risk["AAPL"], SymbolRisk)
    assert risk["AAPL"].price == Decimal("190")
    assert risk["AAPL"].average_volume == Decimal("50000000")
    assert risk["AAPL"].market_cap == Decimal("3.0E12")


def test_to_symbol_risk_passes_through_missing_volume_and_cap():
    ctx = MarketContext(symbols={"AAPL": SymbolData(symbol="AAPL", price="190")})
    risk = ctx.to_symbol_risk()
    assert risk["AAPL"].average_volume is None
    assert risk["AAPL"].market_cap is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_models_market_context.py -v`
Expected: FAIL with `ImportError: cannot import name 'MarketContext'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/rh_wizard/models/market.py` (keep the existing `SymbolRisk`; add the import):

```python
from rh_wizard.models.signals import Signal


class SymbolData(pydantic.BaseModel):
    """Resolved per-symbol facts merged from one or more DataSources (spec §11).

    Every field except ``symbol`` is optional — the resolver degrades and reports, so an
    absent fact is a ``None`` field (a per-symbol gap), not an error.
    """

    symbol: str
    price: Decimal | None = None
    average_volume: Decimal | None = None
    market_cap: Decimal | None = None
    pe_ratio: Decimal | None = None
    pb_ratio: Decimal | None = None
    sector: str | None = None
    industry: str | None = None
    week_52_high: Decimal | None = None
    week_52_low: Decimal | None = None
    dividend_yield: Decimal | None = None


class MarketContext(pydantic.BaseModel):
    """Resolved market data for a candidate universe (spec §7).

    Records what was requested, what each symbol resolved to, which needed signals no
    source could provide (``unmet_signals``), and any per-source fetch errors (``notes``),
    so the Phase 4 cycle can decide whether to proceed. The resolver itself never aborts.
    """

    requested: list[Signal] = []
    symbols: dict[str, SymbolData] = {}
    unmet_signals: list[Signal] = []  # needed but no source provides them
    notes: list[str] = []  # per-source fetch errors / partial-data notes

    def to_symbol_risk(self) -> dict[str, SymbolRisk]:
        """Bridge to the Phase 2 risk engine. Only symbols with a price become a
        ``SymbolRisk`` (its ``price`` is mandatory); volume/market-cap pass through."""
        out: dict[str, SymbolRisk] = {}
        for symbol, data in self.symbols.items():
            if data.price is None:
                continue
            out[symbol] = SymbolRisk(
                symbol=symbol,
                price=data.price,
                average_volume=data.average_volume,
                market_cap=data.market_cap,
            )
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_models_market_context.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/models/market.py tests/unit/test_models_market_context.py
git commit -m "feat: add SymbolData and MarketContext (to_symbol_risk bridge)"
```

---

### Task 3: `DataSource` Protocol + `data/` package

The pluggable seam (spec §6). A `runtime_checkable` Protocol so tests can assert structural conformance.

**Files:**
- Create: `src/rh_wizard/data/__init__.py` (empty)
- Create: `src/rh_wizard/data/base.py`
- Test: `tests/unit/test_data_source_protocol.py`

**Interfaces:**
- Consumes: `Signal` (Task 1), `SymbolData` (Task 2).
- Produces (in `data/base.py`):
  - `DataSource` (`@runtime_checkable` Protocol): attribute `name: str`; `provides(self) -> set[Signal]`; `fetch(self, symbols: list[str], signals: set[Signal]) -> dict[str, SymbolData]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_data_source_protocol.py
from rh_wizard.data.base import DataSource
from rh_wizard.models.market import SymbolData
from rh_wizard.models.signals import Signal


class _ConformingSource:
    name = "fake"

    def provides(self) -> set[Signal]:
        return {Signal.PRICE}

    def fetch(self, symbols, signals) -> dict[str, SymbolData]:
        return {s: SymbolData(symbol=s, price="1") for s in symbols}


class _NonConformingSource:
    name = "broken"
    # missing provides() and fetch()


def test_conforming_source_is_a_datasource():
    assert isinstance(_ConformingSource(), DataSource)


def test_nonconforming_source_is_not_a_datasource():
    assert not isinstance(_NonConformingSource(), DataSource)


def test_protocol_methods_callable_on_conformer():
    src = _ConformingSource()
    assert src.provides() == {Signal.PRICE}
    assert src.fetch(["AAPL"], {Signal.PRICE})["AAPL"].price is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_data_source_protocol.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rh_wizard.data'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/rh_wizard/data/__init__.py
```

```python
# src/rh_wizard/data/base.py
"""The pluggable data-source seam (spec §3/§5/§6).

A source declares the signals it can supply (``provides``) and fetches them for a set of
symbols (``fetch``). Robinhood is the only v1 source; EDGAR / AlphaVantage (and any future
structured source) implement this same Protocol. News/sentiment is NOT a DataSource — the
Phase 4 research agent supplies it via its own web tools.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rh_wizard.models.market import SymbolData
from rh_wizard.models.signals import Signal


@runtime_checkable
class DataSource(Protocol):
    name: str

    def provides(self) -> set[Signal]:
        """The signals this source can supply."""
        ...

    def fetch(self, symbols: list[str], signals: set[Signal]) -> dict[str, SymbolData]:
        """Fetch the requested (already ``provides() ∩ needed``) signals for ``symbols``.

        Returns a per-symbol ``SymbolData`` (absent facts left as ``None``). May raise on
        I/O failure — the resolver catches it and degrades.
        """
        ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_data_source_protocol.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/data/__init__.py src/rh_wizard/data/base.py tests/unit/test_data_source_protocol.py
git commit -m "feat: add DataSource Protocol and data/ package"
```

---

### Task 4: Broker — `get_equity_fundamentals`

Add the fundamentals call to the single MCP-aware module, following the existing `get_equity_quotes` pattern. The payload shape is **unconfirmed** (resolved live in Task 8), so the unwrap is defensive.

**Files:**
- Modify: `src/rh_wizard/broker/client.py`
- Test: `tests/unit/test_broker_fundamentals.py`

**Interfaces:**
- Consumes: existing `_call`, `_extract_list` (in `broker/client.py`).
- Produces (on `BrokerClient`): `get_equity_fundamentals(self, symbols: list[str]) -> list[dict]` — one fundamentals dict per symbol; `[]` for empty input (no tool call).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_broker_fundamentals.py
from rh_wizard.broker.client import BrokerClient


class ScriptedMCPClient:
    """Returns queued raw tool results in order and records each call's args."""

    def __init__(self, results):
        self._results = list(results)
        self.calls = []
        self.entered = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *exc):
        return False

    def list_tools_sync(self):
        return []

    def call_tool_sync(self, *, tool_use_id, name, arguments=None):
        assert self.entered
        assert tool_use_id
        self.calls.append((name, arguments))
        return self._results.pop(0)


def test_get_equity_fundamentals_returns_list_and_forwards_symbols():
    result = {"data": {"results": [{"symbol": "AAPL", "market_cap": "3.0E12"}]}}
    fake = ScriptedMCPClient([result])
    with BrokerClient(fake) as broker:
        rows = broker.get_equity_fundamentals(["AAPL"])
    assert rows[0]["symbol"] == "AAPL"
    assert rows[0]["market_cap"] == "3.0E12"
    assert fake.calls[0] == ("get_equity_fundamentals", {"symbols": ["AAPL"]})


def test_get_equity_fundamentals_tolerates_fundamentals_key():
    result = {"data": {"fundamentals": [{"symbol": "MSFT", "pe_ratio": "35"}]}}
    fake = ScriptedMCPClient([result])
    with BrokerClient(fake) as broker:
        rows = broker.get_equity_fundamentals(["MSFT"])
    assert rows[0]["symbol"] == "MSFT"


def test_get_equity_fundamentals_empty_short_circuits():
    fake = ScriptedMCPClient([])  # no result needed; must not call the tool
    with BrokerClient(fake) as broker:
        assert broker.get_equity_fundamentals([]) == []
    assert fake.calls == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_broker_fundamentals.py -v`
Expected: FAIL with `AttributeError: 'BrokerClient' object has no attribute 'get_equity_fundamentals'`.

- [ ] **Step 3: Write minimal implementation**

In `src/rh_wizard/broker/client.py`, add this method to `BrokerClient` (place it after `get_equity_quotes`):

```python
    def get_equity_fundamentals(self, symbols: list[str]) -> list[dict]:
        """Return one fundamentals dict per symbol (market cap, avg volume, P/E, P/B,
        sector/industry, 52-wk range, dividend).

        Payload shape unconfirmed until live verification (Phase 3, spec §18) — defensively
        unwrap ``data.results``/``data.fundamentals``, tolerating a flat list.
        """
        if not symbols:
            return []
        payload = self._call("get_equity_fundamentals", symbols=list(symbols))
        return _extract_list(payload, "results") or _extract_list(payload, "fundamentals")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_broker_fundamentals.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/broker/client.py tests/unit/test_broker_fundamentals.py
git commit -m "feat: add BrokerClient.get_equity_fundamentals"
```

---

### Task 5: `RobinhoodDataSource` — quotes + fundamentals → `SymbolData`

Wrap the broker as a `DataSource`: `PRICE` from quotes, the rest from fundamentals, parsed defensively into `SymbolData`. Only calls the tools it needs for the requested signals.

**Files:**
- Create: `src/rh_wizard/data/robinhood.py`
- Test: `tests/unit/test_robinhood_source.py`

**Interfaces:**
- Consumes: `Signal` (Task 1), `SymbolData` (Task 2); a broker exposing `get_equity_quotes(symbols)` and `get_equity_fundamentals(symbols)` (Task 4).
- Produces (in `data/robinhood.py`):
  - `RobinhoodDataSource` with `name = "robinhood"`, `__init__(self, broker)`, `provides() -> set[Signal]` (the 10 implemented signals), `fetch(symbols, signals) -> dict[str, SymbolData]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_robinhood_source.py
from decimal import Decimal

from rh_wizard.data.robinhood import RobinhoodDataSource
from rh_wizard.models.signals import Signal


class FakeBroker:
    def __init__(self):
        self.quote_calls = 0
        self.fundamentals_calls = 0

    def get_equity_quotes(self, symbols):
        self.quote_calls += 1
        return [{"symbol": s, "last_trade_price": "190.00"} for s in symbols]

    def get_equity_fundamentals(self, symbols):
        self.fundamentals_calls += 1
        return [
            {"symbol": s, "average_volume": "50000000", "market_cap": "3.0E12",
             "pe_ratio": "30", "sector": "Technology"}
            for s in symbols
        ]


def test_provides_lists_the_implemented_signals():
    src = RobinhoodDataSource(FakeBroker())
    provided = src.provides()
    assert Signal.PRICE in provided
    assert Signal.MARKET_CAP in provided
    assert Signal.DIVIDEND_YIELD in provided
    # declared seams are NOT provided
    assert Signal.NEWS not in provided
    assert Signal.HISTORICALS not in provided


def test_fetch_populates_price_from_quotes_and_facts_from_fundamentals():
    src = RobinhoodDataSource(FakeBroker())
    data = src.fetch(["AAPL"], {Signal.PRICE, Signal.MARKET_CAP, Signal.SECTOR})
    d = data["AAPL"]
    assert d.price == Decimal("190.00")
    assert d.market_cap == Decimal("3.0E12")
    assert d.sector == "Technology"


def test_fetch_only_quotes_when_only_price_requested():
    broker = FakeBroker()
    RobinhoodDataSource(broker).fetch(["AAPL"], {Signal.PRICE})
    assert broker.quote_calls == 1
    assert broker.fundamentals_calls == 0


def test_fetch_only_fundamentals_when_price_not_requested():
    broker = FakeBroker()
    RobinhoodDataSource(broker).fetch(["AAPL"], {Signal.MARKET_CAP})
    assert broker.quote_calls == 0
    assert broker.fundamentals_calls == 1


def test_fetch_ignores_unprovided_signals():
    broker = FakeBroker()
    # NEWS is not provided -> nothing requested that needs a call
    data = RobinhoodDataSource(broker).fetch(["AAPL"], {Signal.NEWS})
    assert broker.quote_calls == 0
    assert broker.fundamentals_calls == 0
    assert data == {}


def test_fetch_empty_symbols_returns_empty():
    broker = FakeBroker()
    assert RobinhoodDataSource(broker).fetch([], {Signal.PRICE}) == {}
    assert broker.quote_calls == 0


def test_fetch_leaves_missing_facts_as_none():
    class ThinBroker(FakeBroker):
        def get_equity_fundamentals(self, symbols):
            return [{"symbol": s, "market_cap": "3.0E12"} for s in symbols]  # no pe_ratio

    data = RobinhoodDataSource(ThinBroker()).fetch(["AAPL"], {Signal.MARKET_CAP, Signal.PE_RATIO})
    assert data["AAPL"].market_cap == Decimal("3.0E12")
    assert data["AAPL"].pe_ratio is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_robinhood_source.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rh_wizard.data.robinhood'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/rh_wizard/data/robinhood.py
"""Robinhood as a DataSource (spec §11).

Quotes supply ``PRICE``; fundamentals supply ``AVERAGE_VOLUME`` / ``MARKET_CAP`` /
``PE_RATIO`` / ``PB_RATIO`` / ``SECTOR`` / ``INDUSTRY`` / 52-week range / ``DIVIDEND_YIELD``.
Wraps the typed ``BrokerClient``. Fundamentals field names are confirmed live (spec §18);
the candidate keys below are best-effort until then.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from rh_wizard.models.market import SymbolData
from rh_wizard.models.signals import Signal

_PROVIDED: frozenset[Signal] = frozenset(
    {
        Signal.PRICE,
        Signal.AVERAGE_VOLUME,
        Signal.MARKET_CAP,
        Signal.PE_RATIO,
        Signal.PB_RATIO,
        Signal.SECTOR,
        Signal.INDUSTRY,
        Signal.WEEK_52_HIGH,
        Signal.WEEK_52_LOW,
        Signal.DIVIDEND_YIELD,
    }
)


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _first(raw: dict, *keys: str) -> Any:
    for k in keys:
        v = raw.get(k)
        if v not in (None, ""):
            return v
    return None


def _quote_price(quote: dict) -> Decimal | None:
    for key in ("last_trade_price", "price", "last_price", "mark_price"):
        v = quote.get(key)
        if v is not None:
            return _to_decimal(v)
    return None


def _parse_fundamentals(raw: dict) -> dict[str, Any]:
    """Map a fundamentals row to SymbolData fields. Candidate keys are confirmed live
    (spec §18) — Task 8 adjusts them and removes the unused fallbacks."""
    return {
        "average_volume": _to_decimal(
            _first(raw, "average_volume", "average_daily_volume", "volume")
        ),
        "market_cap": _to_decimal(_first(raw, "market_cap", "market_capitalization")),
        "pe_ratio": _to_decimal(_first(raw, "pe_ratio", "price_earnings_ratio", "pe")),
        "pb_ratio": _to_decimal(_first(raw, "pb_ratio", "price_book_ratio", "pb")),
        "sector": _first(raw, "sector"),
        "industry": _first(raw, "industry"),
        "week_52_high": _to_decimal(
            _first(raw, "high_52_weeks", "week_52_high", "fifty_two_week_high")
        ),
        "week_52_low": _to_decimal(
            _first(raw, "low_52_weeks", "week_52_low", "fifty_two_week_low")
        ),
        "dividend_yield": _to_decimal(_first(raw, "dividend_yield")),
    }


class RobinhoodDataSource:
    name = "robinhood"

    def __init__(self, broker: Any) -> None:
        self._broker = broker

    def provides(self) -> set[Signal]:
        return set(_PROVIDED)

    def fetch(self, symbols: list[str], signals: set[Signal]) -> dict[str, SymbolData]:
        wanted = signals & _PROVIDED
        if not symbols or not wanted:
            return {}
        fields: dict[str, dict[str, Any]] = {sym: {} for sym in symbols}

        if Signal.PRICE in wanted:
            for q in self._broker.get_equity_quotes(symbols):
                sym = q.get("symbol")
                if sym in fields:
                    fields[sym]["price"] = _quote_price(q)

        # Any non-price provided signal is sourced from the fundamentals call.
        if wanted - {Signal.PRICE}:
            for row in self._broker.get_equity_fundamentals(symbols):
                sym = row.get("symbol")
                if sym in fields:
                    fields[sym].update(_parse_fundamentals(row))

        return {sym: SymbolData(symbol=sym, **vals) for sym, vals in fields.items()}
```

> **Note (DRY):** `_quote_price` duplicates the 4-line helper in `memory/portfolio.py`. It is re-defined here to keep `data/` decoupled from `memory/` (different responsibility). This is an accepted small duplication — do not import across the two packages.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_robinhood_source.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/data/robinhood.py tests/unit/test_robinhood_source.py
git commit -m "feat: add RobinhoodDataSource (quotes + fundamentals -> SymbolData)"
```

---

### Task 6: `SignalResolver` — route, merge, degrade → `MarketContext`

Ask each source for `provides() ∩ needed`, fetch, merge per-symbol results, and assemble a `MarketContext`. Never raises: an unprovided needed signal lands in `unmet_signals`; a source that errors lands in `notes`.

**Files:**
- Create: `src/rh_wizard/data/resolver.py`
- Test: `tests/unit/test_signal_resolver.py`

**Interfaces:**
- Consumes: `DataSource` (Task 3), `Signal` (Task 1), `MarketContext`/`SymbolData` (Task 2).
- Produces (in `data/resolver.py`):
  - `SignalResolver(sources: Sequence[DataSource])` with `resolve(universe: list[str], needed: set[Signal]) -> MarketContext`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_signal_resolver.py
from decimal import Decimal

from rh_wizard.data.resolver import SignalResolver
from rh_wizard.models.market import SymbolData
from rh_wizard.models.signals import Signal


class FakeSource:
    def __init__(self, name, provided, rows=None, raises=False):
        self.name = name
        self._provided = set(provided)
        self._rows = rows or {}
        self._raises = raises
        self.fetch_calls = 0

    def provides(self):
        return set(self._provided)

    def fetch(self, symbols, signals):
        self.fetch_calls += 1
        if self._raises:
            raise RuntimeError("boom")
        return {s: self._rows[s] for s in symbols if s in self._rows}


def test_resolve_merges_two_sources():
    prices = FakeSource("quotes", {Signal.PRICE},
                        {"AAPL": SymbolData(symbol="AAPL", price="190")})
    fundamentals = FakeSource("fundamentals", {Signal.MARKET_CAP},
                              {"AAPL": SymbolData(symbol="AAPL", market_cap="3.0E12")})
    ctx = SignalResolver([prices, fundamentals]).resolve(
        ["AAPL"], {Signal.PRICE, Signal.MARKET_CAP}
    )
    assert ctx.symbols["AAPL"].price == Decimal("190")
    assert ctx.symbols["AAPL"].market_cap == Decimal("3.0E12")
    assert ctx.unmet_signals == []
    assert ctx.notes == []


def test_resolve_records_unmet_signal_with_no_provider():
    prices = FakeSource("quotes", {Signal.PRICE},
                        {"AAPL": SymbolData(symbol="AAPL", price="190")})
    ctx = SignalResolver([prices]).resolve(["AAPL"], {Signal.PRICE, Signal.EARNINGS})
    assert ctx.unmet_signals == [Signal.EARNINGS]
    assert ctx.symbols["AAPL"].price == Decimal("190")  # still resolves what it can


def test_resolve_skips_source_not_covering_needed_signals():
    fundamentals = FakeSource("fundamentals", {Signal.MARKET_CAP},
                              {"AAPL": SymbolData(symbol="AAPL", market_cap="3.0E12")})
    ctx = SignalResolver([fundamentals]).resolve(["AAPL"], {Signal.PRICE})
    assert fundamentals.fetch_calls == 0  # provides ∩ needed is empty
    assert ctx.unmet_signals == [Signal.PRICE]


def test_resolve_degrades_on_source_error():
    good = FakeSource("quotes", {Signal.PRICE},
                      {"AAPL": SymbolData(symbol="AAPL", price="190")})
    bad = FakeSource("fundamentals", {Signal.MARKET_CAP}, raises=True)
    ctx = SignalResolver([good, bad]).resolve(["AAPL"], {Signal.PRICE, Signal.MARKET_CAP})
    assert ctx.symbols["AAPL"].price == Decimal("190")  # the good source still applied
    assert any("fundamentals fetch failed" in n for n in ctx.notes)
    # MARKET_CAP had a provider (it just errored) -> a note, NOT an unmet signal
    assert Signal.MARKET_CAP not in ctx.unmet_signals


def test_resolve_seeds_every_universe_symbol():
    ctx = SignalResolver([]).resolve(["AAPL", "MSFT"], {Signal.PRICE})
    assert set(ctx.symbols) == {"AAPL", "MSFT"}
    assert ctx.symbols["AAPL"].price is None
    assert ctx.requested == [Signal.PRICE]
    assert ctx.unmet_signals == [Signal.PRICE]  # no sources at all
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_signal_resolver.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rh_wizard.data.resolver'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/rh_wizard/data/resolver.py
"""Route the signals a strategy needs to the sources that provide them, and merge the
results into a MarketContext (spec §11).

Always degrades and reports: a needed signal no source provides is recorded in
``unmet_signals``; a source whose ``fetch`` raises is recorded in ``notes``; a per-symbol
missing fact is just a ``None`` field. The resolver never raises — spec §13's "abort the
cycle" decision lives in the Phase 4 cycle, which inspects the returned MarketContext.
"""

from __future__ import annotations

from collections.abc import Sequence

from rh_wizard.data.base import DataSource
from rh_wizard.models.market import MarketContext, SymbolData
from rh_wizard.models.signals import Signal


def _merge(base: SymbolData, incoming: SymbolData) -> SymbolData:
    """Overlay ``incoming``'s non-None facts onto ``base`` (later source wins a conflict)."""
    updates = {
        k: v for k, v in incoming.model_dump().items() if k != "symbol" and v is not None
    }
    return base.model_copy(update=updates) if updates else base


class SignalResolver:
    def __init__(self, sources: Sequence[DataSource]) -> None:
        self._sources = list(sources)

    def resolve(self, universe: list[str], needed: set[Signal]) -> MarketContext:
        symbols: dict[str, SymbolData] = {sym: SymbolData(symbol=sym) for sym in universe}
        notes: list[str] = []
        provided: set[Signal] = set()

        for source in self._sources:
            covers = source.provides() & needed
            if not covers:
                continue
            try:
                fetched = source.fetch(list(universe), covers)
            except Exception as exc:  # degrade-and-report; the cycle decides whether to abort
                notes.append(f"{source.name} fetch failed: {exc}")
                continue
            provided |= covers
            for sym, data in fetched.items():
                if sym in symbols:
                    symbols[sym] = _merge(symbols[sym], data)

        return MarketContext(
            requested=sorted(needed, key=lambda s: s.value),
            symbols=symbols,
            unmet_signals=sorted(needed - provided, key=lambda s: s.value),
            notes=notes,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_signal_resolver.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/data/resolver.py tests/unit/test_signal_resolver.py
git commit -m "feat: add SignalResolver (route, merge, degrade -> MarketContext)"
```

---

### Task 7: `wizard data SYMBOLS...` CLI command

A thin read-only inspection command that resolves a `MarketContext` for the given symbols and renders it — the parallel to `wizard positions`, and the path used for live verification in Task 8.

**Files:**
- Create: `src/rh_wizard/cli/market.py`
- Modify: `src/rh_wizard/cli/render.py`
- Modify: `src/rh_wizard/cli/app.py`
- Test: `tests/unit/test_cli_data.py`

**Interfaces:**
- Consumes: `auth._build_broker` (existing), `load_settings` (existing), `RobinhoodDataSource` (Task 5), `SignalResolver` (Task 6), `MarketContext` (Task 2).
- Produces:
  - `cli/market.py`: `run_data(symbols: list[str]) -> None`.
  - `cli/render.py`: `render_market_context(context) -> str`.
  - `cli/app.py`: a `data` command invoking `run_data`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_cli_data.py
from typer.testing import CliRunner

from rh_wizard.cli import auth
from rh_wizard.cli.app import app

runner = CliRunner()


class FakeBroker:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_equity_quotes(self, symbols):
        return [{"symbol": s, "last_trade_price": "190.00"} for s in symbols]

    def get_equity_fundamentals(self, symbols):
        return [
            {"symbol": s, "average_volume": "50000000", "market_cap": "3000000000000",
             "pe_ratio": "30", "sector": "Technology"}
            for s in symbols
        ]


def test_data_command_renders_resolved_market_data(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))  # isolate from real config
    monkeypatch.setattr(auth, "_build_broker", lambda settings: FakeBroker())
    result = runner.invoke(app, ["data", "aapl"])
    assert result.exit_code == 0
    assert "AAPL" in result.output  # upper-cased
    assert "$190.00" in result.output  # price
    assert "Technology" in result.output  # sector


def test_data_command_reports_unmet_and_uppercases(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))
    monkeypatch.setattr(auth, "_build_broker", lambda settings: FakeBroker())
    result = runner.invoke(app, ["data", "msft"])
    assert result.exit_code == 0
    assert "MSFT" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli_data.py -v`
Expected: FAIL — `data` is not a registered command (Typer exits non-zero / "No such command").

- [ ] **Step 3: Write minimal implementation**

```python
# src/rh_wizard/cli/market.py
"""`wizard data SYMBOLS...` — resolve and show market data for a few symbols.

A thin, read-only inspection command (and the live-verification path for the data layer),
paralleling `wizard positions`. Resolves every signal the Robinhood source provides.
"""

from __future__ import annotations

import typer

from rh_wizard.cli import auth
from rh_wizard.cli.render import render_market_context
from rh_wizard.config.settings import load_settings
from rh_wizard.data.resolver import SignalResolver
from rh_wizard.data.robinhood import RobinhoodDataSource


def run_data(symbols: list[str]) -> None:
    settings = load_settings()
    broker = auth._build_broker(settings)
    source = RobinhoodDataSource(broker)
    universe = [s.upper() for s in symbols]
    with broker:
        context = SignalResolver([source]).resolve(universe, source.provides())
    typer.echo(render_market_context(context))
```

Append to `src/rh_wizard/cli/render.py`:

```python
def render_market_context(context) -> str:
    """Render a MarketContext as a table plus any unmet-signal / note lines."""
    from rich.table import Table

    table = Table(title="Market data")
    table.add_column("Symbol")
    table.add_column("Price", justify="right")
    table.add_column("Avg Vol", justify="right")
    table.add_column("Mkt Cap", justify="right")
    table.add_column("P/E", justify="right")
    table.add_column("Sector")
    for sym, d in context.symbols.items():
        table.add_row(
            sym,
            fmt_money(d.price),
            fmt_num(d.average_volume),
            fmt_money(d.market_cap),
            fmt_num(d.pe_ratio),
            d.sector or "-",
        )
    body = render_to_str(table) if context.symbols else "No symbols.\n"
    if context.unmet_signals:
        body += "Unmet signals: " + ", ".join(s.value for s in context.unmet_signals) + "\n"
    for note in context.notes:
        body += f"Note: {note}\n"
    return body
```

In `src/rh_wizard/cli/app.py`, add the import (next to the other `cli` imports) and the command. Import:

```python
from rh_wizard.cli.market import run_data
```

Command (place after the `history` command):

```python
@app.command()
def data(
    symbols: list[str] = typer.Argument(..., help="Ticker symbols, e.g. AAPL MSFT."),
) -> None:
    """Resolve and show market data (quotes + fundamentals) for SYMBOLS."""
    run_data(symbols)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_cli_data.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/cli/market.py src/rh_wizard/cli/render.py src/rh_wizard/cli/app.py tests/unit/test_cli_data.py
git commit -m "feat: add wizard data command (render resolved MarketContext)"
```

---

### Task 8: Live fundamentals shape verification (opt-in) + spec §18 update

Confirm the real `get_equity_fundamentals` payload shape against the live MCP server, adjust `_parse_fundamentals` candidate keys to the confirmed names, and record the findings in the spec — mirroring Phase 1's live shape verification.

**Files:**
- Create: `tests/integration/test_live_fundamentals.py`
- Modify (after the live run): `src/rh_wizard/data/robinhood.py` (`_parse_fundamentals` keys), `docs/superpowers/specs/2026-06-21-robinhood-wizard-design.md` (§18).

**Interfaces:**
- Consumes: `auth._build_broker`, `load_settings`, `RobinhoodDataSource` (Task 5), `SignalResolver` (Task 6).
- Produces: an opt-in (`RH_WIZARD_LIVE=1`) test that prints the raw fundamentals keys + resolved `SymbolData` and asserts a price resolves.

- [ ] **Step 1: Write the live test (skipped unless `RH_WIZARD_LIVE=1`)**

```python
# tests/integration/test_live_fundamentals.py
"""Live, opt-in shape verification for fundamentals against the real Robinhood MCP.

Run explicitly (needs a cached token from `wizard auth login`):
    RH_WIZARD_LIVE=1 uv run pytest tests/integration/test_live_fundamentals.py -v -s

Prints the raw fundamentals keys and the resolved SymbolData so the parser can be pinned
to the confirmed field names (spec §18).
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RH_WIZARD_LIVE") != "1",
    reason="set RH_WIZARD_LIVE=1 to run the live fundamentals test",
)


def test_fundamentals_shape_live():
    from rh_wizard.cli import auth
    from rh_wizard.config.settings import load_settings
    from rh_wizard.data.resolver import SignalResolver
    from rh_wizard.data.robinhood import RobinhoodDataSource

    settings = load_settings()
    broker = auth._build_broker(settings)
    source = RobinhoodDataSource(broker)
    with broker:
        raw = broker.get_equity_fundamentals(["AAPL"])
        context = SignalResolver([source]).resolve(["AAPL", "MSFT"], source.provides())

    print("\nRaw fundamentals[0] keys:", sorted(raw[0].keys()) if raw else "none")
    for sym, d in context.symbols.items():
        print(
            f"{sym}: price={d.price} vol={d.average_volume} cap={d.market_cap} "
            f"pe={d.pe_ratio} pb={d.pb_ratio} sector={d.sector} industry={d.industry}"
        )
    print(f"Unmet: {context.unmet_signals}  Notes: {context.notes}")

    assert "AAPL" in context.symbols
    assert context.symbols["AAPL"].price is not None  # quotes path confirmed live in Phase 1
```

- [ ] **Step 2: Verify it is collected but skipped without the flag**

Run: `uv run pytest tests/integration/test_live_fundamentals.py -v`
Expected: 1 skipped (reason: "set RH_WIZARD_LIVE=1 ...").

- [ ] **Step 3: Run it live and read the output**

Run: `RH_WIZARD_LIVE=1 uv run pytest tests/integration/test_live_fundamentals.py -v -s`
Expected: PASS, printing the raw fundamentals keys and resolved `SymbolData`. Read the printed `Raw fundamentals[0] keys` and the per-symbol line.

- [ ] **Step 4: Pin `_parse_fundamentals` to the confirmed keys**

In `src/rh_wizard/data/robinhood.py`, edit `_parse_fundamentals` so each `_first(...)` lists the **confirmed** live key first (keep one defensive fallback only where the live payload was ambiguous; drop candidates the live run proved unused). If a field (e.g. `pe_ratio` or `market_cap`) is absent from the live payload, note it — that fact stays `None` and the signal remains a per-symbol gap (it is not "unprovided"; the source still advertises it).

Re-run the offline source tests to confirm no regression:

Run: `uv run pytest tests/unit/test_robinhood_source.py tests/unit/test_signal_resolver.py -v`
Expected: PASS.

- [ ] **Step 5: Record the confirmed shape in the spec (§18)**

In `docs/superpowers/specs/2026-06-21-robinhood-wizard-design.md`, append a subsection under §18 (next to "Phase 1 read shapes — RESOLVED live") titled **"Phase 3 fundamentals shape — RESOLVED live (2026-06-23)"**, listing: the wrapper key (`data.results` vs `data.fundamentals`), the confirmed field names for market cap / average volume / P-E / P-B / sector / industry / 52-wk range / dividend yield, and any field Robinhood does **not** supply (so the strategy/research layer knows not to rely on it).

- [ ] **Step 6: Commit**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pytest`

```bash
git add tests/integration/test_live_fundamentals.py src/rh_wizard/data/robinhood.py docs/superpowers/specs/2026-06-21-robinhood-wizard-design.md
git commit -m "test: live-verify fundamentals shape; pin parser and record in spec §18"
```

---

## Final Verification

- [ ] **Run the full suite + lint**

Run: `uv run pytest && uv run ruff check . && uv run ruff format --check .`
Expected: all green (the live test is skipped without `RH_WIZARD_LIVE=1`).

- [ ] **Open the PR**

```bash
git push -u origin phase-3
gh pr create --title "Phase 3: data layer + SignalResolver" \
  --body "Implements the structured data layer (Signal taxonomy, DataSource seam, RobinhoodDataSource, SignalResolver -> MarketContext -> SymbolRisk) per spec §17 Phase 3. Web/news deferred to Phase 4 as agent tools. Fundamentals shape live-verified (spec §18)."
```

---

## Self-Review (completed during planning)

**Spec coverage (§5/§6/§11/§17 Phase 3):**
- `DataSource` interface (declares provided signals) → Task 3. ✅
- `RobinhoodDataSource` → Task 5 (+ broker `get_equity_fundamentals`, Task 4). ✅
- `WebResearchDataSource` → **deliberately deferred** to Phase 4 as agent tools (Design Decision #1); the `NEWS`/`SENTIMENT` seams exist in the taxonomy (Task 1). ✅
- `SignalResolver` routes needed → provided into a `MarketContext` → Task 6. ✅
- `MarketContext` (resolved market data for the universe) → Task 2; bridges to the risk engine via `to_symbol_risk` (closes Phase 2 decision #1). ✅
- Fundamentals signals (market cap, P/E, P/B, avg volume, sector/industry, 52-wk, dividend) → Tasks 1/5. ✅
- Deep financial-statement factors (EDGAR/AlphaVantage) → out of scope (spec §11/§20); the `DataSource` seam admits them later. ✅
- Testing: offline unit tests with fakes + opt-in live shape verification (spec §14) → Tasks 1–7 / Task 8. ✅

**Placeholder scan:** No TBD/TODO/"handle edge cases" — every code step shows complete code; Task 8's "pin to confirmed keys" is an explicit live-data step, not a placeholder.

**Type consistency:** `Signal` (Task 1) used identically in Tasks 2/3/5/6; `SymbolData`/`MarketContext` (Task 2) consumed by Tasks 3/5/6/7; `RobinhoodDataSource.fetch(symbols, signals) -> dict[str, SymbolData]` matches the `DataSource` Protocol (Task 3) and the resolver's call (Task 6); `get_equity_fundamentals(symbols) -> list[dict]` defined in Task 4 and consumed in Task 5/8. ✅
