# Research Mode (detached holdings + capital override) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two composable `wizard run` flags — `--capital N` and `--ignore-holdings` — that override the post-reconcile `PortfolioState` so a strategy can be run as a read-only, no-orders research/what-if (e.g. for a friend, or with a hypothetical amount).

**Architecture:** Approach 1 from the spec — one pure `apply_override()` applied to the `PortfolioState` **between `reconcile()` and `enrich_with_quotes()`** in `run_cycle`. Every downstream stage (universe, research, plan, allocator, risk) is untouched because it still just reads `PortfolioState`. Execution is blocked at three layers (CLI guard, no executor built, `_execute` already no-ops outside `HUMAN_APPROVAL`).

**Tech Stack:** Python 3.12, Pydantic v2, Typer, Rich, pytest. Package manager: `uv`. Money is `Decimal`.

## Global Constraints

- **Run tests with:** `uv run pytest` (config in `pyproject.toml`; `pythonpath=["src"]`, `-q` default).
- **Format before every commit:** `uv run ruff format .` — and lint: `uv run ruff check .` (selects E, F, I, UP, B; line-length 100).
- **Money is `Decimal`.** `--capital` is parsed to `Decimal` via `Decimal(str(value))` to avoid binary-float drift.
- **Branch:** `research-mode-capital-override` is already checked out with the spec committed.
- **The pipeline downstream of reconcile must stay byte-for-byte unchanged** — only the `PortfolioState` they receive changes.
- **A research run must NEVER place an order.**
- **DryRun stays the default.**
- TDD: failing test first, then minimal implementation. Frequent commits.

---

### Task 1: `PortfolioOverride` value object + `apply_override()`

A pure, frozen value object plus the pure function that applies it to a `PortfolioState`. Lives next to `reconcile`/`enrich_with_quotes` in `memory/portfolio.py`.

**Files:**
- Create: `tests/unit/test_portfolio_override.py`
- Modify: `src/rh_wizard/memory/portfolio.py`

**Interfaces:**
- Consumes: `PortfolioState` (from `rh_wizard.models.portfolio`).
- Produces (later tasks rely on these exact names/types):
  - `class PortfolioOverride` with fields `capital: Decimal | None = None`, `ignore_holdings: bool = False`, and a `@property active -> bool` (True iff `capital is not None or ignore_holdings`).
  - `def apply_override(state: PortfolioState, override: PortfolioOverride) -> PortfolioState`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_portfolio_override.py`:

```python
from decimal import Decimal

from rh_wizard.memory.portfolio import PortfolioOverride, apply_override
from rh_wizard.models.portfolio import PortfolioState, Position


def _state():
    return PortfolioState(
        account_number="ACC1",
        positions=[Position(symbol="AAPL", quantity="5", average_cost="90", cost_basis="450")],
        cash=Decimal("1000"),
        buying_power=Decimal("1000"),
    )


def test_inactive_override_is_identity():
    override = PortfolioOverride()
    assert override.active is False
    out = apply_override(_state(), override)
    assert out.cash == Decimal("1000")
    assert out.buying_power == Decimal("1000")
    assert [p.symbol for p in out.positions] == ["AAPL"]


def test_capital_overrides_cash_and_buying_power_as_decimal():
    override = PortfolioOverride(capital=Decimal("10000"))
    assert override.active is True
    out = apply_override(_state(), override)
    assert out.cash == Decimal("10000")
    assert out.buying_power == Decimal("10000")
    assert isinstance(out.cash, Decimal)
    # holdings untouched when only capital is set
    assert [p.symbol for p in out.positions] == ["AAPL"]


def test_ignore_holdings_empties_positions_keeps_cash():
    override = PortfolioOverride(ignore_holdings=True)
    assert override.active is True
    out = apply_override(_state(), override)
    assert out.positions == []
    assert out.cash == Decimal("1000")  # real cash preserved


def test_both_compose():
    override = PortfolioOverride(capital=Decimal("10000"), ignore_holdings=True)
    out = apply_override(_state(), override)
    assert out.positions == []
    assert out.cash == Decimal("10000")
    assert out.buying_power == Decimal("10000")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_portfolio_override.py -q`
Expected: FAIL with `ImportError: cannot import name 'PortfolioOverride'` (or `apply_override`).

- [ ] **Step 3: Write minimal implementation**

In `src/rh_wizard/memory/portfolio.py`, add the import line `from dataclasses import dataclass` at the top of the imports block, and append this dataclass + function at the end of the file:

```python
@dataclass(frozen=True)
class PortfolioOverride:
    """Run-scoped synthetic override of account state (spec §4). ``capital`` replaces cash and
    buying power; ``ignore_holdings`` clears positions. Either makes a run read-only (no orders)."""

    capital: Decimal | None = None
    ignore_holdings: bool = False

    @property
    def active(self) -> bool:
        return self.capital is not None or self.ignore_holdings


def apply_override(state: PortfolioState, override: PortfolioOverride) -> PortfolioState:
    """Apply a PortfolioOverride to a freshly reconciled state (pure; spec §4)."""
    if override.ignore_holdings:
        state = state.model_copy(update={"positions": []})
    if override.capital is not None:
        state = state.model_copy(
            update={"cash": override.capital, "buying_power": override.capital}
        )
    return state
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_portfolio_override.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Format, lint, commit**

```bash
uv run ruff format . && uv run ruff check .
git add src/rh_wizard/memory/portfolio.py tests/unit/test_portfolio_override.py
git commit -m "feat(portfolio): PortfolioOverride + pure apply_override (research mode)"
```

---

### Task 2: Thread `override` through `run_cycle`

Add an optional `override` param to `run_cycle`, apply it between reconcile and enrich, tag `CycleRun.note`, and carry the override onto `CycleResult` so render can detect it. Both flat and bucketed paths inherit it because the override is applied before the `if strategy.buckets:` branch.

**Files:**
- Modify: `src/rh_wizard/core/cycle.py`
- Test: `tests/unit/test_cycle.py`

**Interfaces:**
- Consumes: `PortfolioOverride`, `apply_override` (Task 1).
- Produces:
  - `run_cycle(strategy, deps, mode=CycleMode.DRY_RUN, override: PortfolioOverride | None = None)`.
  - `CycleResult` gains field `override: PortfolioOverride | None = None`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_cycle.py` (the file's `FakeBroker`, `FakeDataSource`, `_deps`, `_RecordingExecutor`, `_YesGate`, `_human_approval` helpers already exist — reuse them):

```python
def test_cycle_override_uses_synthetic_capital_and_ignores_holdings():
    from rh_wizard.memory.portfolio import PortfolioOverride

    strategy = Strategy(id="m", name="M", universe=["AAPL"], signals_needed={Signal.PRICE})

    class HeldBroker(FakeBroker):
        def get_equity_positions(self, account_number):
            return [{"symbol": "MSFT", "quantity": "5", "average_cost": "90"}]

    override = PortfolioOverride(capital=Decimal("500"), ignore_holdings=True)
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal, broker=HeldBroker())
        with deps.broker:
            result = run_cycle(strategy, deps, override=override)
        assert result.run.status == "completed"
        # synthetic capital replaced real cash; held MSFT was ignored
        assert result.portfolio.cash == Decimal("500")
        assert result.portfolio.positions == []
        assert "MSFT" not in result.market.symbols  # holdings not unioned into universe
        assert result.override is override  # carried for rendering
        assert "research" in result.run.note  # journaled tag


def test_cycle_override_never_executes_even_with_executor():
    from rh_wizard.memory.portfolio import PortfolioOverride

    strategy = Strategy(id="m", name="M", universe=["AAPL"], signals_needed={Signal.PRICE})
    override = PortfolioOverride(capital=Decimal("10000"))
    with SqliteJournal(":memory:") as journal:
        deps = _deps(journal)
        ex = _RecordingExecutor()
        deps.executor = ex
        deps.approval = _YesGate()
        with deps.broker:
            # even if a HUMAN_APPROVAL mode is requested, the cycle itself only executes when
            # mode == HUMAN_APPROVAL; the CLI forces DryRun for overrides (Task 3). Here we assert
            # the default DryRun path with an override never touches the executor.
            result = run_cycle(strategy, deps, override=override)
        assert result.orders == []
        assert ex.placed == []
        assert ex.reviewed == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cycle.py::test_cycle_override_uses_synthetic_capital_and_ignores_holdings -q`
Expected: FAIL with `TypeError: run_cycle() got an unexpected keyword argument 'override'`.

- [ ] **Step 3: Write minimal implementation**

In `src/rh_wizard/core/cycle.py`:

(a) Add the import near the other `memory` import:

```python
from rh_wizard.memory.portfolio import PortfolioOverride, apply_override, enrich_with_quotes, reconcile
```

(Replace the existing `from rh_wizard.memory.portfolio import enrich_with_quotes, reconcile` line with the line above.)

(b) Add the `override` field to `CycleResult` (after the `orders` field):

```python
    orders: list[OrderResult] = field(default_factory=list)
    override: PortfolioOverride | None = None
```

(c) Add a small note helper above `run_cycle`:

```python
def _override_note(override: PortfolioOverride) -> str:
    parts: list[str] = []
    if override.capital is not None:
        parts.append(f"capital={override.capital}")
    if override.ignore_holdings:
        parts.append("holdings ignored")
    return "research: " + ", ".join(parts)
```

(d) Change the `run_cycle` signature and the reconcile block. Replace:

```python
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
```

with:

```python
def run_cycle(
    strategy: Strategy,
    deps: CycleDeps,
    mode: CycleMode = CycleMode.DRY_RUN,
    override: PortfolioOverride | None = None,
) -> CycleResult:
    run = CycleRun(
        run_id=uuid.uuid4().hex,
        strategy_id=strategy.id,
        mode=mode.value,
        started_at=_now(),
    )

    # Stage 3 (RECONCILE) — broker is ground truth; failure aborts (spec §13). A research
    # override (spec §4-5) replaces account state between reconcile and enrich.
    try:
        portfolio = reconcile(deps.broker, deps.settings)
        if override is not None and override.active:
            portfolio = apply_override(portfolio, override)
        portfolio = enrich_with_quotes(portfolio, deps.broker)
    except Exception as exc:
        run = run.model_copy(
            update={"status": "aborted", "finished_at": _now(), "note": f"reconcile failed: {exc}"}
        )
        deps.journal.record_run(run)
        return CycleResult(run=run, override=override)
    if override is not None and override.active:
        run = run.model_copy(update={"note": _override_note(override)})
```

(e) Carry the override onto the bucketed return. Replace:

```python
    if strategy.buckets:
        return _run_bucketed(strategy, deps, run, portfolio)
```

with:

```python
    if strategy.buckets:
        result = _run_bucketed(strategy, deps, run, portfolio)
        result.override = override
        return result
```

(f) Carry the override onto the flat success return. In the final `return CycleResult(...)` of `run_cycle` (the one with `orders=orders`), add `override=override,` as the last argument:

```python
    return CycleResult(
        run=run,
        portfolio=portfolio,
        market=market,
        report=report,
        plan=plan,
        vetted=vetted,
        discovery=discovery,
        orders=orders,
        override=override,
    )
```

(g) Carry the override onto the flat research/plan-abort return. Replace:

```python
        return CycleResult(run=run, portfolio=portfolio, market=market, discovery=discovery)
```

with:

```python
        return CycleResult(
            run=run, portfolio=portfolio, market=market, discovery=discovery, override=override
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cycle.py -q`
Expected: PASS — the two new tests plus all pre-existing `test_cycle.py` tests (override defaults to `None`, so existing calls are unaffected).

- [ ] **Step 5: Format, lint, commit**

```bash
uv run ruff format . && uv run ruff check .
git add src/rh_wizard/core/cycle.py tests/unit/test_cycle.py
git commit -m "feat(cycle): apply PortfolioOverride post-reconcile; carry on result + journal note"
```

---

### Task 3: CLI flags, validation, execution lockout

Add `--capital` / `--ignore-holdings` to `wizard run`, validate, force DryRun and build no executor when an override is active, and thread the override into `run_cycle`.

**Files:**
- Modify: `src/rh_wizard/cli/app.py` (the `run` command)
- Modify: `src/rh_wizard/cli/run.py` (`run_strategy`)
- Test: `tests/unit/test_cli_run.py`

**Interfaces:**
- Consumes: `PortfolioOverride` (Task 1), `run_cycle(..., override=...)` (Task 2).
- Produces: `run_strategy(strategy_id, execute=False, capital: Decimal | None = None, ignore_holdings: bool = False)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_cli_run.py` (reuses the module-level `runner`, `FakeBroker`, `FakeStructuredLlm`, `_write_strategy`, and the `auth` / `run_module` imports already at the top):

```python
def test_run_capital_and_ignore_holdings_render_research_banner(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))
    _write_strategy(tmp_path)
    monkeypatch.setattr(auth, "_build_broker", lambda settings: FakeBroker())
    monkeypatch.setattr(run_module, "_build_llm", lambda settings: FakeStructuredLlm())
    result = runner.invoke(app, ["run", "demo", "--capital", "5000", "--ignore-holdings"])
    assert result.exit_code == 0, result.output
    assert "RESEARCH MODE" in result.output
    assert "$5,000.00" in result.output
    assert "holdings ignored" in result.output


def test_run_execute_with_capital_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))
    _write_strategy(tmp_path)
    monkeypatch.setattr(auth, "_build_broker", lambda settings: FakeBroker())
    monkeypatch.setattr(run_module, "_build_llm", lambda settings: FakeStructuredLlm())
    result = runner.invoke(app, ["run", "demo", "--capital", "5000", "--execute"])
    assert result.exit_code != 0
    assert "cannot be combined" in result.output


def test_run_execute_with_ignore_holdings_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))
    _write_strategy(tmp_path)
    monkeypatch.setattr(auth, "_build_broker", lambda settings: FakeBroker())
    monkeypatch.setattr(run_module, "_build_llm", lambda settings: FakeStructuredLlm())
    result = runner.invoke(app, ["run", "demo", "--ignore-holdings", "--execute"])
    assert result.exit_code != 0
    assert "cannot be combined" in result.output


def test_run_non_positive_capital_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))
    _write_strategy(tmp_path)
    monkeypatch.setattr(auth, "_build_broker", lambda settings: FakeBroker())
    monkeypatch.setattr(run_module, "_build_llm", lambda settings: FakeStructuredLlm())
    result = runner.invoke(app, ["run", "demo", "--capital", "0"])
    assert result.exit_code != 0
    assert "positive" in result.output


def test_run_override_builds_no_executor(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))
    _write_strategy(tmp_path)
    built = []
    monkeypatch.setattr(auth, "_build_broker", lambda settings: FakeBroker())
    monkeypatch.setattr(run_module, "_build_llm", lambda settings: FakeStructuredLlm())
    monkeypatch.setattr(run_module, "_build_executor", lambda broker: built.append(1))
    result = runner.invoke(app, ["run", "demo", "--capital", "5000"])
    assert result.exit_code == 0, result.output
    assert built == []  # no executor constructed for a research run
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_cli_run.py -q -k "research_banner or rejected or no_executor"`
Expected: FAIL — `--capital`/`--ignore-holdings` are not yet options (Typer error "No such option"), so exit codes/output won't match.

- [ ] **Step 3a: Implement the CLI options in `cli/app.py`**

Add `from decimal import Decimal` to the imports at the top of `src/rh_wizard/cli/app.py`. Replace the entire `run` command with:

```python
@app.command()
def run(
    strategy_id: str = typer.Argument(..., help="Strategy id (yaml filename stem)."),  # noqa: B008
    execute: bool = typer.Option(  # noqa: B008
        False,
        "--execute",
        help="Place REAL orders after a typed confirmation (HumanApproval). "
        "Default is DryRun (no orders).",
    ),
    capital: float | None = typer.Option(  # noqa: B008
        None,
        "--capital",
        help="Size to this dollar amount instead of your account's cash (research/what-if; "
        "no orders).",
    ),
    ignore_holdings: bool = typer.Option(  # noqa: B008
        False,
        "--ignore-holdings",
        help="Treat your account as having no positions — a clean slate (research/what-if; "
        "no orders).",
    ),
) -> None:
    """Run STRATEGY_ID. Default is DryRun — proposes a vetted plan and places NO orders.
    With --execute: places REAL orders after a typed confirmation (HumanApproval).
    With --capital/--ignore-holdings: a read-only research/what-if run (never places orders)."""
    cap = Decimal(str(capital)) if capital is not None else None
    run_strategy(strategy_id, execute=execute, capital=cap, ignore_holdings=ignore_holdings)
```

- [ ] **Step 3b: Implement validation + lockout in `cli/run.py`**

In `src/rh_wizard/cli/run.py`, replace the existing import
`from rh_wizard.memory.portfolio import resolve_account_number` with:

```python
from rh_wizard.memory.portfolio import PortfolioOverride, resolve_account_number
```

Do **not** add `from decimal import Decimal` here: `run.py` already has `from __future__ import
annotations`, so the `Decimal | None` annotation is a string and never evaluated at runtime — an
actual import would be flagged unused (ruff F401). The `capital <= 0` comparison works on the
`Decimal` value passed in from `app.py` without importing the type.

Replace the whole `run_strategy` function with:

```python
def run_strategy(
    strategy_id: str,
    execute: bool = False,
    capital: Decimal | None = None,
    ignore_holdings: bool = False,
) -> None:
    paths.ensure_home()
    settings = load_settings()
    registry = StrategyRegistry(paths.strategies_dir())
    try:
        strategy = registry.load(strategy_id)
    except StrategyNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc

    override = PortfolioOverride(capital=capital, ignore_holdings=ignore_holdings)
    if execute and override.active:
        raise typer.BadParameter(
            "--execute cannot be combined with --capital/--ignore-holdings; "
            "research/what-if runs never place orders."
        )
    if capital is not None and capital <= 0:
        raise typer.BadParameter("--capital must be a positive dollar amount.")
    do_execute = execute and not override.active

    broker = auth._build_broker(settings)
    with broker, SqliteJournal(paths.db_path()) as journal:
        # Resolve the trading account up front so the data layer can call account-scoped tools
        # (get_equity_tradability, for the fractionable signal) correctly.
        account_number = resolve_account_number(broker, settings)
        resolver = SignalResolver([RobinhoodDataSource(broker, account_number)])
        llm = _build_llm(settings)
        researcher = (
            _build_web_researcher(settings) if strategy.web_research else LlmResearcher(llm)
        )
        deps = CycleDeps(
            broker=broker,
            settings=settings,
            resolver=resolver,
            researcher=researcher,
            planner=LlmPlanner(llm),
            journal=journal,
            discoverer=(
                _build_discoverer(settings)
                if strategy.discover or any(b.discover for b in strategy.buckets)
                else None
            ),
            recommender=_build_recommender(settings) if strategy.buckets else None,
            executor=_build_executor(broker) if do_execute else None,
            approval=_build_approval() if do_execute else None,
        )
        mode = CycleMode.HUMAN_APPROVAL if do_execute else CycleMode.DRY_RUN
        result = run_cycle(strategy, deps, mode, override=override if override.active else None)
    typer.echo(render_cycle_result(result))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli_run.py -q`
Expected: PASS — the five new tests plus all pre-existing CLI tests. (The banner assertions in `test_run_capital_and_ignore_holdings_render_research_banner` depend on Task 4; if running tasks strictly in order, see the note below.)

> **Ordering note:** the banner text (`RESEARCH MODE`, `$5,000.00`, `holdings ignored`) is produced by Task 4's render change. If you implement strictly task-by-task, `test_run_capital_and_ignore_holdings_render_research_banner` will fail until Task 4 lands. Two options: (a) implement Task 4 immediately after Task 3 Step 3 and before this Step 4; or (b) temporarily narrow this run to the non-banner tests with `-k "rejected or no_executor"`, commit, then complete Task 4. The other four tests in this task pass independently of Task 4.

- [ ] **Step 5: Format, lint, commit**

```bash
uv run ruff format . && uv run ruff check .
git add src/rh_wizard/cli/app.py src/rh_wizard/cli/run.py tests/unit/test_cli_run.py
git commit -m "feat(cli): --capital/--ignore-holdings research flags; block --execute; force DryRun"
```

---

### Task 4: Research-mode render banner

Prepend an unmistakable banner to a completed run's render when its override was active.

**Files:**
- Modify: `src/rh_wizard/cli/render.py` (`render_cycle_result`)
- Test: `tests/unit/test_render_cycle.py`

**Interfaces:**
- Consumes: `CycleResult.override` (Task 2) — accessed via attributes (`active`, `capital`, `ignore_holdings`); render stays decoupled and does not import `PortfolioOverride`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_render_cycle.py` (reuses the `_run()` helper and existing imports; add the `PortfolioOverride` import):

```python
def test_render_shows_research_banner_when_override_active():
    from rh_wizard.memory.portfolio import PortfolioOverride

    result = CycleResult(
        run=_run(),
        portfolio=PortfolioState(
            account_number="ACC1",
            positions=[],
            cash=Decimal("5000"),
            buying_power=Decimal("5000"),
            total_value=Decimal("5000"),
        ),
        vetted=VettedPlan(
            approved=[TradeIntent(side="buy", symbol="AAPL", quantity="1", limit_price="190")]
        ),
        override=PortfolioOverride(capital=Decimal("5000"), ignore_holdings=True),
    )
    out = render_cycle_result(result)
    assert "RESEARCH MODE" in out
    assert "$5,000.00" in out  # capital clause
    assert "holdings ignored" in out


def test_render_has_no_banner_on_normal_run():
    result = CycleResult(
        run=_run(),
        portfolio=PortfolioState(
            account_number="ACC1",
            positions=[],
            cash=Decimal("10000"),
            buying_power=Decimal("10000"),
            total_value=Decimal("10000"),
        ),
        vetted=VettedPlan(approved=[]),
    )
    out = render_cycle_result(result)
    assert "RESEARCH MODE" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_render_cycle.py::test_render_shows_research_banner_when_override_active -q`
Expected: FAIL — no `RESEARCH MODE` text in output.

- [ ] **Step 3: Write minimal implementation**

In `src/rh_wizard/cli/render.py`, add this helper just above `render_cycle_result`:

```python
def _research_banner(override) -> str:
    """Banner for a research/what-if run (override active). Empty string otherwise."""
    if override is None or not getattr(override, "active", False):
        return ""
    clauses = []
    if override.capital is not None:
        clauses.append(f"capital={fmt_money(override.capital)}")
    if override.ignore_holdings:
        clauses.append("holdings ignored")
    return "🔬 RESEARCH MODE — no orders placed · " + " · ".join(clauses)
```

Then in `render_cycle_result`, after the line `lines = [header]`, insert:

```python
    banner = _research_banner(getattr(result, "override", None))
    if banner:
        lines.insert(0, banner)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_render_cycle.py -q`
Expected: PASS — the two new tests plus all pre-existing render tests.

- [ ] **Step 5: Format, lint, commit**

```bash
uv run ruff format . && uv run ruff check .
git add src/rh_wizard/cli/render.py tests/unit/test_render_cycle.py
git commit -m "feat(render): research-mode banner for overridden runs"
```

---

### Task 5: Full-suite verification

Confirm the whole change is green and the pipeline is untouched.

**Files:** none (verification only).

- [ ] **Step 1: Run the full unit suite**

Run: `uv run pytest -q`
Expected: PASS — all tests, including the pre-existing `test_cycle.py`, `test_cli_run.py`, `test_render_cycle.py`, `test_deploy_purity.py`, and `test_risk_engine_purity.py` (the override does not touch the allocator or risk engine, so the purity guards stay green).

- [ ] **Step 2: Lint + format check**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: no errors, no files would be reformatted.

- [ ] **Step 3: Manual smoke check of the help text** (optional but recommended)

Run: `uv run wizard run --help`
Expected: `--capital` and `--ignore-holdings` appear with their help strings; `--execute` still present.

- [ ] **Step 4: Final commit (only if Step 2 reformatted anything)**

```bash
git add -A
git commit -m "chore: format + lint pass for research mode"
```

---

## Self-Review (completed by plan author)

- **Spec coverage:** §4 `PortfolioOverride`/`apply_override` → Task 1. §5 apply-between-reconcile-and-enrich + `run_cycle` param + flat/bucketed inheritance → Task 2. §6 CLI flags, three-layer lockout, `Decimal(str(...))`, `--capital ≤ 0` guard → Task 3. §7 render banner + `CycleRun.note` tag (note in Task 2, banner in Task 4) → Tasks 2 & 4. §8 testing → tests embedded in every task + Task 5 full suite. §9 files-touched all appear. No gaps.
- **Placeholder scan:** none — every code/test step contains complete content and exact commands.
- **Type consistency:** `PortfolioOverride(capital: Decimal | None, ignore_holdings: bool, active: property)` and `apply_override(state, override) -> PortfolioState` are used identically in Tasks 2–4. `run_cycle(..., override=...)` matches between Task 2 (definition) and Task 3 (call). `CycleResult.override` is set in Task 2 and read in Task 4. `_research_banner`/`_override_note` names are each defined once and referenced consistently.
- **Cross-task ordering caveat** explicitly flagged in Task 3 Step 4 (banner test depends on Task 4).
