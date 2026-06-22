# Robinhood Wizard — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read-only broker integration — reconcile live Robinhood state into a `PortfolioState`, persist order history in a SQLite `Journal`, and surface both through `wizard positions` and `wizard history`. Also clears the three Phase 0 deferred cleanups from spec §18.

**Architecture:** Extend the existing `BrokerClient` (the single MCP-aware module) with typed, **read-only** tool wrappers (`get_portfolio`, `get_equity_positions`, `get_equity_quotes`, `get_equity_orders`), all auto-paginating. A pure `reconcile()` turns live broker data into a `PortfolioState` (broker is ground truth — we never trust local state for holdings); a best-effort `enrich_with_quotes()` adds market value and return. A `SqliteJournal` stores `TradeRecord`s keyed by broker order id (idempotent upsert), populated by `sync_equity_orders()` from the broker's order history. Two new CLI commands render these with `rich`. No order placement, cancellation, or LLM calls exist in this phase.

**Tech Stack:** Python 3.12, `uv`, `pydantic` v2, `typer`, `rich` (added this phase), `mcp` 1.28.x via `strands-agents`, `pytest`, `ruff`.

## Global Constraints

Every task implicitly includes these (values copied verbatim from the spec):

- **Python:** `requires-python = ">=3.12"`; `target-version = "py312"`.
- **Lint/format:** `ruff` with `select = ["E", "F", "I", "UP", "B"]`, `line-length = 100`. Every task ends green on `uv run ruff check .` and `uv run ruff format --check .`.
- **Tests:** `uv run pytest` (configured `-q`, `pythonpath = ["src"]`, `testpaths = ["tests"]`). No network or LLM in unit tests — use fakes. Live tests are env-gated behind `RH_WIZARD_LIVE=1`.
- **Money is `Decimal`.** Never use `float` for prices, quantities, cash, or P/L. MCP returns numeric strings; parse with `Decimal(str(value))`.
- **Broker is ground truth (spec §4.3).** Holdings/cash/buying-power come from a live reconcile every time; nothing is read from local state as "what we hold."
- **Read-only this phase.** No `place_*`, `cancel_*`, or `review_*` order tools are called. Phase 1 touches only read endpoints.
- **Secrets & PII hygiene (spec §19).** No credentials, tokens, or **account numbers** ever appear unmasked in logs or user-facing output. Account numbers are masked to the last 4 characters in all rendered output. Test fixtures use fake account numbers only — never a real one in the repo.
- **Runtime state location:** all runtime files live under `RH_WIZARD_HOME` (default `~/.rh-wizard/`); tests set it to `tmp_path`. Nothing user-specific is committed.

**Branch:** `main` is the default branch and is clean. Create and work on a `phase-1` branch (`git switch -c phase-1`) before Task 1; open a PR at the end.

---

## File Structure

**New files:**
- `src/rh_wizard/models/__init__.py` — new `models/` package (shared Pydantic models, per spec §15).
- `src/rh_wizard/models/portfolio.py` — `Position`, `PortfolioState`.
- `src/rh_wizard/models/trade.py` — `TradeRecord`.
- `src/rh_wizard/memory/__init__.py` — new `memory/` package.
- `src/rh_wizard/memory/portfolio.py` — account selection + `reconcile()` + `enrich_with_quotes()`.
- `src/rh_wizard/memory/journal.py` — `SqliteJournal`.
- `src/rh_wizard/memory/sync.py` — `sync_equity_orders()` (broker order history → journal).
- `src/rh_wizard/logging/mcp_noise.py` — silence the benign MCP session-termination warning (cleanup §18.5).
- `src/rh_wizard/cli/render.py` — `mask_account` (cleanup §18.5), rich render helpers.
- `src/rh_wizard/cli/portfolio.py` — `run_positions()`, `run_history()`.
- `tests/unit/test_mcp_noise.py`, `tests/unit/test_render.py`, `tests/unit/test_models_portfolio.py`, `tests/unit/test_models_trade.py`, `tests/unit/test_broker_reads.py`, `tests/unit/test_account_selection.py`, `tests/unit/test_reconcile.py`, `tests/unit/test_enrich.py`, `tests/unit/test_journal.py`, `tests/unit/test_sync.py`, `tests/unit/test_cli_portfolio.py`, `tests/unit/test_cli_history.py`
- `tests/integration/test_live_portfolio.py` — env-gated live shape verification.

**Modified files:**
- `src/rh_wizard/config/settings.py` — add optional `account_number` pin.
- `src/rh_wizard/cli/auth.py` — mask account numbers in `run_accounts` (cleanup §18.5).
- `src/rh_wizard/cli/app.py` — register `positions`/`history`; install the MCP-noise filter.
- `src/rh_wizard/broker/client.py` — add read-only tool wrappers + pagination helpers.
- `tests/unit/test_cli_auth.py` — update for masked account output.
- `pyproject.toml` / `uv.lock` — add `rich`.
- `config.example.yaml` — document the optional `account_number`.
- `README.md` — Phase 1 usage.

**Deleted files (cleanup §18.5 — decide on unused `OAuthCallbackServer`):**
- `src/rh_wizard/auth/callback.py`
- `tests/unit/test_callback.py`

---

## Phase 0 Deferred Cleanups (spec §18.5) — where they land

| Cleanup | Decision | Task |
|---|---|---|
| Account numbers not masked in user-facing output | Add `mask_account` (last-4); apply to `accounts`, `positions`, `history` | **Task 3** (+ used in 11, 14) |
| Benign `"Session termination failed: 400"` warning on MCP context exit | Suppress via a targeted logging filter on `mcp.client.streamable_http`; keep all other warnings | **Task 2** |
| Unused `OAuthCallbackServer` localhost listener | **Remove it.** The paste-based callback is the proven WSL-robust flow (§18.3) and is the only consumer path; the listener has no caller and is dead code in a credential-handling OSS repo. Recoverable from git history if a non-WSL localhost flow is ever wanted. | **Task 1** |

---

### Task 1: Remove the unused `OAuthCallbackServer` (cleanup §18.5)

`OAuthCallbackServer` / `CallbackResult` in `auth/callback.py` are referenced only by their own unit test — `cli/auth.py` builds the redirect URI as a plain string and uses the paste-based handler. Delete the dead module per YAGNI and clean-public-surface (§19).

**Files:**
- Delete: `src/rh_wizard/auth/callback.py`
- Delete: `tests/unit/test_callback.py`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing (removal only). `cli/auth.py:_redirect_uri` is unaffected (it constructs the URI string itself).

- [ ] **Step 1: Confirm there are no other references**

Run: `grep -rn "callback import\|OAuthCallbackServer\|CallbackResult" src/ tests/`
Expected: matches ONLY in `src/rh_wizard/auth/callback.py` and `tests/unit/test_callback.py`. (The `/callback` string literal in `cli/auth.py:_redirect_uri` is unrelated and must remain.)

- [ ] **Step 2: Delete the module and its test**

```bash
git rm src/rh_wizard/auth/callback.py tests/unit/test_callback.py
```

- [ ] **Step 3: Verify the suite still passes**

Run: `uv run pytest -q`
Expected: PASS (the removed test is gone; nothing else imported the module).

- [ ] **Step 4: Lint**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: remove unused OAuthCallbackServer (paste-based flow is the proven path)"
```

---

### Task 2: Silence the benign MCP session-termination warning (cleanup §18.5)

On MCP context exit the SDK logs `WARNING "Session termination failed: 400"` from `mcp.client.streamable_http` (verified at `streamable_http.py:591,593`). It is cosmetic. Drop exactly that message on that logger; let every other warning through.

**Files:**
- Create: `src/rh_wizard/logging/mcp_noise.py`
- Create: `tests/unit/test_mcp_noise.py`
- Modify: `src/rh_wizard/cli/app.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `silence_session_termination_warning() -> None` (idempotent; mirrors `install_redaction`'s idempotency style).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_mcp_noise.py
import logging

from rh_wizard.logging.mcp_noise import silence_session_termination_warning

LOGGER_NAME = "mcp.client.streamable_http"


def test_drops_session_termination_warning(caplog):
    silence_session_termination_warning()
    logger = logging.getLogger(LOGGER_NAME)
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        logger.warning("Session termination failed: 400")
    assert "Session termination failed" not in caplog.text


def test_keeps_other_warnings(caplog):
    silence_session_termination_warning()
    logger = logging.getLogger(LOGGER_NAME)
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        logger.warning("A real problem happened")
    assert "A real problem happened" in caplog.text


def test_is_idempotent():
    silence_session_termination_warning()
    silence_session_termination_warning()
    logger = logging.getLogger(LOGGER_NAME)
    from rh_wizard.logging.mcp_noise import _SessionTerminationFilter

    assert sum(isinstance(f, _SessionTerminationFilter) for f in logger.filters) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_mcp_noise.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rh_wizard.logging.mcp_noise'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/rh_wizard/logging/mcp_noise.py
"""Suppress one benign MCP SDK warning without hiding real ones.

On context exit the mcp Streamable-HTTP client logs
``WARNING "Session termination failed: <status>"`` (Robinhood's terminate endpoint
returns 400). It is cosmetic. We drop exactly that message on that logger and let every
other record through.
"""

from __future__ import annotations

import logging

_LOGGER_NAME = "mcp.client.streamable_http"


class _SessionTerminationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not record.getMessage().startswith("Session termination failed")


def silence_session_termination_warning() -> None:
    logger = logging.getLogger(_LOGGER_NAME)
    if not any(isinstance(f, _SessionTerminationFilter) for f in logger.filters):
        logger.addFilter(_SessionTerminationFilter())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_mcp_noise.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Install it at CLI startup**

In `src/rh_wizard/cli/app.py`, modify `main()` to call the new function alongside the existing redaction install. Replace the existing `main` and add the import:

```python
# add to the imports near the top of cli/app.py
from rh_wizard.logging.mcp_noise import silence_session_termination_warning
```

```python
# replace the existing main() in cli/app.py with:
def main() -> None:
    logging.basicConfig(level=logging.INFO)
    install_redaction(logging.getLogger())
    silence_session_termination_warning()
    app()
```

- [ ] **Step 6: Verify suite + lint**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/rh_wizard/logging/mcp_noise.py tests/unit/test_mcp_noise.py src/rh_wizard/cli/app.py
git commit -m "fix: silence benign MCP session-termination warning (§18.5)"
```

---

### Task 3: Mask account numbers in user-facing output (cleanup §18.5)

Add a `mask_account` display helper and apply it where account numbers are printed today (`wizard accounts`). It will also be used by `positions`/`history` later. This is presentation masking (last-4 visible), distinct from the log-redaction filter.

**Files:**
- Create: `src/rh_wizard/cli/render.py`
- Create: `tests/unit/test_render.py`
- Modify: `src/rh_wizard/cli/auth.py`
- Modify: `tests/unit/test_cli_auth.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `mask_account(value: str, visible: int = 4) -> str` — returns the value with all but the last `visible` characters replaced by `*`; values of length `<= visible` are returned unchanged.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_render.py
from rh_wizard.cli.render import mask_account


def test_masks_all_but_last_four():
    assert mask_account("ACC123456") == "*****3456"


def test_short_values_unchanged():
    assert mask_account("12") == "12"


def test_coerces_non_str():
    assert mask_account(1234567) == "***4567"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_render.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rh_wizard.cli.render'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/rh_wizard/cli/render.py
"""User-facing rendering helpers (terminal output).

``mask_account`` is presentation masking — it shows only the last few characters of an
account number, per the Robinhood tool guide. This is separate from
``rh_wizard.logging.redaction`` (which scrubs secrets from logs).
"""

from __future__ import annotations


def mask_account(value: str, visible: int = 4) -> str:
    s = str(value)
    if len(s) <= visible:
        return s
    return "*" * (len(s) - visible) + s[-visible:]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_render.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Apply masking in `run_accounts`**

In `src/rh_wizard/cli/auth.py`, add the import and rewrite `run_accounts` to mask the `account_number` field before printing.

```python
# add to imports in cli/auth.py
from rh_wizard.cli.render import mask_account
```

```python
# replace the existing run_accounts() in cli/auth.py with:
def run_accounts() -> None:
    settings = load_settings()
    broker = _build_broker(settings)
    with broker:
        accounts = broker.get_accounts()
    for acct in accounts:
        shown = dict(acct)
        if "account_number" in shown:
            shown["account_number"] = mask_account(str(shown["account_number"]))
        typer.echo(redact(str(shown)))
```

- [ ] **Step 6: Update the existing accounts CLI test for masking**

In `tests/unit/test_cli_auth.py`, replace `test_accounts_command_prints_accounts` so it asserts the masked form (the `FakeBroker` returns `account_number="AG-123"`, which masks to `**-123`):

```python
def test_accounts_command_masks_account_number(monkeypatch):
    monkeypatch.setattr(auth, "_build_broker", lambda settings: FakeBroker())
    result = runner.invoke(app, ["accounts"])
    assert result.exit_code == 0
    assert "AG-123" not in result.output  # full number never shown
    assert "**-123" in result.output  # last-4 visible
```

- [ ] **Step 7: Run the affected tests**

Run: `uv run pytest tests/unit/test_render.py tests/unit/test_cli_auth.py -v`
Expected: PASS.

- [ ] **Step 8: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/cli/render.py tests/unit/test_render.py src/rh_wizard/cli/auth.py tests/unit/test_cli_auth.py
git commit -m "feat: mask account numbers in user-facing output (§18.5)"
```

---

### Task 4: Add `rich` + shared render primitives

Add the `rich` dependency (spec §16) and the small formatting primitives all tables share: `render_to_str` (renders any rich renderable to a string for both terminal output and tests) and the `Decimal`-safe cell formatters.

**Files:**
- Modify: `pyproject.toml` (and `uv.lock` via `uv add`)
- Modify: `src/rh_wizard/cli/render.py`
- Modify: `tests/unit/test_render.py`

**Interfaces:**
- Consumes: `mask_account` (Task 3).
- Produces (all in `cli/render.py`):
  - `render_to_str(renderable, width: int = 100) -> str`
  - `fmt_money(value) -> str` — `"-"` for `None`, else `f"${value:,.2f}"`.
  - `fmt_pct(value) -> str` — `"-"` for `None`, else `f"{value:,.2f}%"`.
  - `fmt_num(value) -> str` — `"-"` for `None`, else `str(value)`.

- [ ] **Step 1: Add the dependency**

Run: `uv add "rich>=13"`
Expected: `pyproject.toml` gains `rich>=13` under `[project].dependencies`; `uv.lock` updates; `rich` installs into `.venv`.

- [ ] **Step 2: Write the failing test**

Append to `tests/unit/test_render.py`:

```python
from decimal import Decimal

from rh_wizard.cli.render import fmt_money, fmt_num, fmt_pct, render_to_str


def test_render_to_str_outputs_text():
    from rich.table import Table

    table = Table()
    table.add_column("Symbol")
    table.add_row("AAPL")
    out = render_to_str(table)
    assert "AAPL" in out


def test_formatters_handle_none():
    assert fmt_money(None) == "-"
    assert fmt_pct(None) == "-"
    assert fmt_num(None) == "-"


def test_formatters_format_decimals():
    assert fmt_money(Decimal("1234.5")) == "$1,234.50"
    # 12.349 rounds unambiguously to 12.35 (avoid the half-even tie at .345).
    assert fmt_pct(Decimal("12.349")) == "12.35%"
    assert fmt_num(Decimal("10")) == "10"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_render.py -v`
Expected: FAIL with `ImportError: cannot import name 'render_to_str'`.

- [ ] **Step 4: Implement the primitives**

Append to `src/rh_wizard/cli/render.py`:

```python
def render_to_str(renderable, width: int = 100) -> str:
    """Render any rich renderable (or plain string) to text — for echo and for tests."""
    import io

    from rich.console import Console

    buf = io.StringIO()
    Console(file=buf, width=width, no_color=True).print(renderable)
    return buf.getvalue()


def fmt_money(value) -> str:
    return "-" if value is None else f"${value:,.2f}"


def fmt_pct(value) -> str:
    return "-" if value is None else f"{value:,.2f}%"


def fmt_num(value) -> str:
    return "-" if value is None else str(value)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_render.py -v`
Expected: PASS.

- [ ] **Step 6: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add pyproject.toml uv.lock src/rh_wizard/cli/render.py tests/unit/test_render.py
git commit -m "feat: add rich and shared render primitives"
```

---

### Task 5: Shared models — `Position` and `PortfolioState`

The Pydantic models reconciliation produces (spec §7). Money fields are `Decimal`. Enrichment fields are optional (populated later by `enrich_with_quotes`).

**Files:**
- Create: `src/rh_wizard/models/__init__.py` (empty)
- Create: `src/rh_wizard/models/portfolio.py`
- Create: `tests/unit/test_models_portfolio.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Position(symbol: str, quantity: Decimal, average_cost: Decimal, cost_basis: Decimal, current_price: Decimal | None = None, market_value: Decimal | None = None, unrealized_pl: Decimal | None = None, unrealized_pl_pct: Decimal | None = None)`
  - `PortfolioState(account_number: str, positions: list[Position], cash: Decimal, buying_power: Decimal, market_value: Decimal | None = None, total_value: Decimal | None = None, total_return_pct: Decimal | None = None)`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_models_portfolio.py
from decimal import Decimal

from rh_wizard.models.portfolio import PortfolioState, Position


def test_position_coerces_string_numbers_to_decimal():
    p = Position(symbol="AAPL", quantity="10", average_cost="100.25", cost_basis="1002.50")
    assert p.quantity == Decimal("10")
    assert p.average_cost == Decimal("100.25")
    assert p.current_price is None  # enrichment fields default to None


def test_portfolio_state_defaults():
    state = PortfolioState(
        account_number="ACC1",
        positions=[],
        cash=Decimal("500"),
        buying_power=Decimal("500"),
    )
    assert state.positions == []
    assert state.market_value is None
    assert state.total_value is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_models_portfolio.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rh_wizard.models'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/rh_wizard/models/__init__.py
```

```python
# src/rh_wizard/models/portfolio.py
"""Live portfolio models (spec §7). Money/quantities are Decimal."""

from __future__ import annotations

from decimal import Decimal

import pydantic


class Position(pydantic.BaseModel):
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    cost_basis: Decimal
    # Enrichment (best-effort, from quotes) — None until enrich_with_quotes runs.
    current_price: Decimal | None = None
    market_value: Decimal | None = None
    unrealized_pl: Decimal | None = None
    unrealized_pl_pct: Decimal | None = None


class PortfolioState(pydantic.BaseModel):
    account_number: str
    positions: list[Position]
    cash: Decimal
    buying_power: Decimal
    # Aggregate enrichment — None until enrich_with_quotes runs.
    market_value: Decimal | None = None
    total_value: Decimal | None = None
    total_return_pct: Decimal | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_models_portfolio.py -v`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/models/__init__.py src/rh_wizard/models/portfolio.py tests/unit/test_models_portfolio.py
git commit -m "feat: add Position and PortfolioState models"
```

---

### Task 6: Broker read wrappers — `get_portfolio` + `get_equity_positions` (paginated)

Add the first read-only tool wrappers to `BrokerClient`, plus the shared pagination helpers `_extract_list` and `_next_cursor`. `get_equity_positions` follows the `next`/`cursor` pages until exhausted (spec §11; tool docs say "pass the cursor query param from the prior response's next URL").

> **Payload-shape note:** only `get_accounts` (`data.accounts`) is live-verified (§18.4). Positions/portfolio nesting keys (`data.positions`, money field names) are *assumed* and confirmed in **Task 15**. Keep parsing defensive (try `data.<key>`, then `<key>`, then `results`).

**Files:**
- Modify: `src/rh_wizard/broker/client.py`
- Create: `tests/unit/test_broker_reads.py`

**Interfaces:**
- Consumes: existing `BrokerClient._call` / `_coerce_payload`.
- Produces (methods on `BrokerClient`):
  - `get_portfolio(self, account_number: str) -> dict` — returns the coerced payload dict.
  - `get_equity_positions(self, account_number: str) -> list[dict]` — all pages, flattened.
  - Module helpers `_extract_list(payload: dict, key: str) -> list[dict]` and `_next_cursor(payload: dict) -> str | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_broker_reads.py
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
        assert self.entered, "must be used inside the client context"
        assert tool_use_id
        self.calls.append((name, arguments))
        return self._results.pop(0)


def test_get_portfolio_returns_payload():
    result = {"data": {"buying_power": "500.00", "cash": "250.00"}}
    fake = ScriptedMCPClient([result])
    with BrokerClient(fake) as broker:
        payload = broker.get_portfolio("ACC1")
    assert payload["data"]["buying_power"] == "500.00"
    assert fake.calls[0] == ("get_portfolio", {"account_number": "ACC1"})


def test_get_equity_positions_paginates():
    page1 = {"data": {"positions": [{"symbol": "AAPL"}], "next": "https://x/y?cursor=abc"}}
    page2 = {"data": {"positions": [{"symbol": "MSFT"}], "next": None}}
    fake = ScriptedMCPClient([page1, page2])
    with BrokerClient(fake) as broker:
        positions = broker.get_equity_positions("ACC1")
    assert [p["symbol"] for p in positions] == ["AAPL", "MSFT"]
    # second page carried the cursor extracted from page1's next URL
    assert fake.calls[1] == ("get_equity_positions", {"account_number": "ACC1", "cursor": "abc"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_broker_reads.py -v`
Expected: FAIL with `AttributeError: 'BrokerClient' object has no attribute 'get_portfolio'`.

- [ ] **Step 3: Write minimal implementation**

In `src/rh_wizard/broker/client.py`, add these methods to `BrokerClient` (right after `get_accounts`):

```python
    def get_portfolio(self, account_number: str) -> dict:
        return self._call("get_portfolio", account_number=account_number)

    def get_equity_positions(self, account_number: str) -> list[dict]:
        return self._paginate(
            "get_equity_positions", "positions", account_number=account_number
        )

    def _paginate(self, name: str, key: str, **arguments: Any) -> list[dict]:
        """Follow ``next`` cursors, flattening the ``key`` list across all pages."""
        items: list[dict] = []
        cursor: str | None = None
        while True:
            args = {**arguments, "cursor": cursor} if cursor else dict(arguments)
            payload = self._call(name, **args)
            items.extend(_extract_list(payload, key))
            cursor = _next_cursor(payload)
            if not cursor:
                return items
```

And add these module-level helpers (after `_coerce_payload`):

```python
def _extract_list(payload: dict, key: str) -> list[dict]:
    """Pull a results list out of a tool payload, tolerant of nesting shape."""
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get(key), list):
        return data[key]
    if isinstance(payload.get(key), list):
        return payload[key]
    if isinstance(payload.get("results"), list):
        return payload["results"]
    return []


def _next_cursor(payload: dict) -> str | None:
    """Extract the ``cursor`` query param from a payload's ``next`` URL, if any."""
    from urllib.parse import parse_qs, urlsplit

    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    nxt = data.get("next") if isinstance(data, dict) else None
    if not isinstance(nxt, str) or not nxt:
        return None
    return (parse_qs(urlsplit(nxt).query).get("cursor") or [None])[0]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_broker_reads.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run full broker suite + lint**

Run: `uv run pytest tests/unit/test_broker_client.py tests/unit/test_broker_reads.py -q && uv run ruff check . && uv run ruff format --check .`
Expected: PASS (existing `test_broker_client.py` still green).

- [ ] **Step 6: Commit**

```bash
git add src/rh_wizard/broker/client.py tests/unit/test_broker_reads.py
git commit -m "feat: add get_portfolio and paginated get_equity_positions"
```

---

### Task 7: Broker read wrappers — `get_equity_quotes` + `get_equity_orders` (paginated)

Add the remaining read endpoints. `get_equity_quotes` is single-shot (≤20 symbols is fine for v1 universes; quotes still return above 20 but closes are omitted — tool docs). `get_equity_orders` paginates like positions and forwards optional filters.

> **Payload-shape note:** quote field names and the orders nesting key (`data.orders`) are assumed and confirmed in **Task 15**.

**Files:**
- Modify: `src/rh_wizard/broker/client.py`
- Modify: `tests/unit/test_broker_reads.py`

**Interfaces:**
- Consumes: `_call`, `_paginate`, `_extract_list` (Task 6).
- Produces (methods on `BrokerClient`):
  - `get_equity_quotes(self, symbols: list[str]) -> list[dict]` — `[]` for empty input.
  - `get_equity_orders(self, account_number: str, *, created_at_gte: str | None = None, state: str | None = None, placed_agent: str | None = None) -> list[dict]` — all pages, flattened.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_broker_reads.py`:

```python
def test_get_equity_quotes_extracts_list():
    result = {"data": {"quotes": [{"symbol": "AAPL", "last_trade_price": "190.00"}]}}
    fake = ScriptedMCPClient([result])
    with BrokerClient(fake) as broker:
        quotes = broker.get_equity_quotes(["AAPL"])
    assert quotes[0]["symbol"] == "AAPL"
    assert fake.calls[0] == ("get_equity_quotes", {"symbols": ["AAPL"]})


def test_get_equity_quotes_empty_short_circuits():
    fake = ScriptedMCPClient([])  # no result needed; should not call the tool
    with BrokerClient(fake) as broker:
        assert broker.get_equity_quotes([]) == []
    assert fake.calls == []


def test_get_equity_orders_paginates_and_forwards_filters():
    page1 = {"data": {"orders": [{"id": "O1"}], "next": "https://x/y?cursor=n2"}}
    page2 = {"data": {"orders": [{"id": "O2"}], "next": None}}
    fake = ScriptedMCPClient([page1, page2])
    with BrokerClient(fake) as broker:
        orders = broker.get_equity_orders("ACC1", created_at_gte="2026-01-01")
    assert [o["id"] for o in orders] == ["O1", "O2"]
    assert fake.calls[0] == (
        "get_equity_orders",
        {"account_number": "ACC1", "created_at_gte": "2026-01-01"},
    )
    assert fake.calls[1][1]["cursor"] == "n2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_broker_reads.py -v`
Expected: FAIL with `AttributeError: 'BrokerClient' object has no attribute 'get_equity_quotes'`.

- [ ] **Step 3: Write minimal implementation**

Add to `BrokerClient` in `src/rh_wizard/broker/client.py` (after `get_equity_positions`):

```python
    def get_equity_quotes(self, symbols: list[str]) -> list[dict]:
        if not symbols:
            return []
        payload = self._call("get_equity_quotes", symbols=list(symbols))
        return _extract_list(payload, "quotes")

    def get_equity_orders(
        self,
        account_number: str,
        *,
        created_at_gte: str | None = None,
        state: str | None = None,
        placed_agent: str | None = None,
    ) -> list[dict]:
        args: dict[str, Any] = {"account_number": account_number}
        if created_at_gte:
            args["created_at_gte"] = created_at_gte
        if state:
            args["state"] = state
        if placed_agent:
            args["placed_agent"] = placed_agent
        return self._paginate("get_equity_orders", "orders", **args)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_broker_reads.py -v`
Expected: PASS (5 tests in the file).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/broker/client.py tests/unit/test_broker_reads.py
git commit -m "feat: add get_equity_quotes and paginated get_equity_orders"
```

---

### Task 8: Account selection + `account_number` config pin

Reconciliation must target the dedicated **agentic** account (spec §9). Add `select_account` (and a convenience `resolve_account_number`) plus an optional `account_number` pin in `Settings` so users with multiple accounts can disambiguate.

> **Shape note:** the agentic-account marker field is unverified; match the substring `"agentic"` across candidate type fields, confirmed in **Task 15**. The `account_number` pin is the deterministic escape hatch.

**Files:**
- Modify: `src/rh_wizard/config/settings.py`
- Create: `src/rh_wizard/memory/__init__.py` (empty)
- Create: `src/rh_wizard/memory/portfolio.py`
- Create: `tests/unit/test_account_selection.py`
- Modify: `config.example.yaml`

**Interfaces:**
- Consumes: `BrokerClient.get_accounts` (Phase 0), `mask_account` (Task 3).
- Produces (in `memory/portfolio.py`):
  - `class AccountSelectionError(Exception)`
  - `select_account(accounts: list[dict], pinned: str | None = None) -> dict`
  - `resolve_account_number(broker, settings) -> str`
- Also: `Settings.account_number: str | None = None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_account_selection.py
import pytest

from rh_wizard.config.settings import Settings
from rh_wizard.memory.portfolio import (
    AccountSelectionError,
    resolve_account_number,
    select_account,
)


def test_single_account_is_selected():
    accounts = [{"account_number": "ACC1", "type": "agentic"}]
    assert select_account(accounts)["account_number"] == "ACC1"


def test_pinned_account_is_selected():
    accounts = [{"account_number": "ACC1"}, {"account_number": "ACC2"}]
    assert select_account(accounts, pinned="ACC2")["account_number"] == "ACC2"


def test_agentic_account_chosen_when_multiple():
    # Real Phase 0 shape: agentic account is flagged agentic_allowed=true, not by type.
    accounts = [
        {"account_number": "5PY29149", "type": "margin", "agentic_allowed": False},
        {"account_number": "766943641", "type": "cash", "agentic_allowed": True},
    ]
    assert select_account(accounts)["account_number"] == "766943641"


def test_agentic_account_chosen_by_nickname_fallback():
    accounts = [
        {"account_number": "ACC1", "type": "margin"},
        {"account_number": "ACC2", "type": "cash", "nickname": "Agentic"},
    ]
    assert select_account(accounts)["account_number"] == "ACC2"


def test_ambiguous_multiple_raises():
    accounts = [{"account_number": "ACC1"}, {"account_number": "ACC2"}]
    with pytest.raises(AccountSelectionError):
        select_account(accounts)


def test_empty_raises():
    with pytest.raises(AccountSelectionError):
        select_account([])


def test_pinned_not_found_raises():
    with pytest.raises(AccountSelectionError):
        select_account([{"account_number": "ACC1"}], pinned="NOPE")


def test_resolve_uses_broker_and_settings():
    class FakeBroker:
        def get_accounts(self):
            return [{"account_number": "ACC1", "type": "agentic"}]

    assert resolve_account_number(FakeBroker(), Settings()) == "ACC1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_account_selection.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rh_wizard.memory'`.

- [ ] **Step 3: Add the `account_number` pin to Settings**

In `src/rh_wizard/config/settings.py`, add one field to the `Settings` model (after `oauth_client_name`):

```python
    # Optional: pin which brokerage account to trade in. Leave unset to auto-select the
    # single account, or the one whose type is "agentic" when you have several.
    account_number: str | None = None
```

- [ ] **Step 4: Write minimal implementation**

```python
# src/rh_wizard/memory/__init__.py
```

```python
# src/rh_wizard/memory/portfolio.py
"""Account selection and live reconciliation (spec §8 step 3).

The broker is ground truth: every call here reads live state. Nothing trusts local
storage for holdings.
"""

from __future__ import annotations

from rh_wizard.cli.render import mask_account


class AccountSelectionError(Exception):
    pass


def _is_agentic(account: dict) -> bool:
    # Live-confirmed (Phase 0 §18): the agentic account is a regular account flagged
    # ``agentic_allowed=true`` (nickname "Agentic"), NOT a distinct account "type".
    # Fall back to a substring match across name/type fields for robustness.
    if account.get("agentic_allowed") is True:
        return True
    blob = " ".join(
        str(account.get(k, ""))
        for k in ("nickname", "type", "brokerage_account_type", "account_type")
    ).lower()
    return "agentic" in blob


def select_account(accounts: list[dict], pinned: str | None = None) -> dict:
    if pinned:
        for a in accounts:
            if str(a.get("account_number")) == pinned:
                return a
        raise AccountSelectionError(
            f"Configured account_number {mask_account(pinned)} was not found."
        )
    if not accounts:
        raise AccountSelectionError("No Robinhood accounts found.")
    if len(accounts) == 1:
        return accounts[0]
    agentic = [a for a in accounts if _is_agentic(a)]
    if len(agentic) == 1:
        return agentic[0]
    raise AccountSelectionError(
        "Multiple accounts found; set 'account_number' in ~/.rh-wizard/config.yaml."
    )


def resolve_account_number(broker, settings) -> str:
    account = select_account(broker.get_accounts(), settings.account_number)
    return str(account["account_number"])
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_account_selection.py -v`
Expected: PASS (7 tests).

- [ ] **Step 6: Document the pin in `config.example.yaml`**

Append to `config.example.yaml`:

```yaml

# Optional: pin which brokerage account to use. Leave commented to auto-select.
# account_number: "YOUR_AGENTIC_ACCOUNT_NUMBER"
```

- [ ] **Step 7: Run settings + OSS tests + lint**

Run: `uv run pytest tests/unit/test_settings.py tests/unit/test_oss_files.py tests/unit/test_account_selection.py -q && uv run ruff check . && uv run ruff format --check .`
Expected: PASS (the `account_number` example line is a placeholder, so `test_example_files_have_no_real_secrets` stays green).

- [ ] **Step 8: Commit**

```bash
git add src/rh_wizard/memory/__init__.py src/rh_wizard/memory/portfolio.py src/rh_wizard/config/settings.py config.example.yaml tests/unit/test_account_selection.py
git commit -m "feat: add agentic-account selection and account_number pin"
```

---

### Task 9: Reconciliation core — `reconcile()` → `PortfolioState`

Turn live broker data into a `PortfolioState`: select the account, pull positions, pull the portfolio breakdown for cash/buying-power. No quotes yet (Task 10 enriches). This is the integrity-floor "RECONCILE" step (spec §8 step 3).

> **Shape note:** position field names (`symbol`, `quantity`, `average_cost`/`average_buy_price`) and portfolio money keys are assumed; confirmed in **Task 15**. Parsing is defensive with `Decimal`.

**Files:**
- Modify: `src/rh_wizard/memory/portfolio.py`
- Create: `tests/unit/test_reconcile.py`

**Interfaces:**
- Consumes: `BrokerClient.get_accounts/get_equity_positions/get_portfolio` (Tasks 6), `select_account` (Task 8), `Position`/`PortfolioState` (Task 5).
- Produces (in `memory/portfolio.py`):
  - `reconcile(broker, settings) -> PortfolioState`
  - helpers `_to_position(raw: dict) -> Position`, `_extract_cash(portfolio: dict) -> tuple[Decimal, Decimal]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_reconcile.py
from decimal import Decimal

from rh_wizard.config.settings import Settings
from rh_wizard.memory.portfolio import reconcile


class FakeBroker:
    def get_accounts(self):
        return [{"account_number": "ACC1", "type": "agentic"}]

    def get_equity_positions(self, account_number):
        assert account_number == "ACC1"
        return [{"symbol": "AAPL", "quantity": "10", "average_cost": "100"}]

    def get_portfolio(self, account_number):
        return {"data": {"cash": "500.00", "buying_power": "500.00"}}


def test_reconcile_builds_portfolio_state():
    state = reconcile(FakeBroker(), Settings())
    assert state.account_number == "ACC1"
    assert len(state.positions) == 1
    assert state.positions[0].symbol == "AAPL"
    assert state.positions[0].quantity == Decimal("10")
    assert state.positions[0].cost_basis == Decimal("1000")
    assert state.cash == Decimal("500.00")
    assert state.buying_power == Decimal("500.00")
    # No quotes yet — enrichment fields are None.
    assert state.market_value is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_reconcile.py -v`
Expected: FAIL with `ImportError: cannot import name 'reconcile'`.

- [ ] **Step 3: Write minimal implementation**

Add to `src/rh_wizard/memory/portfolio.py`. First replace the existing import header (from Task 8) so it reads exactly (adds `Decimal` and the portfolio models; keep `mask_account` — do **not** duplicate it):

```python
from __future__ import annotations

from decimal import Decimal

from rh_wizard.cli.render import mask_account
from rh_wizard.models.portfolio import PortfolioState, Position
```

Then append:

```python
def _to_position(raw: dict) -> Position:
    quantity = Decimal(str(raw.get("quantity", "0")))
    average_cost = Decimal(str(raw.get("average_cost", raw.get("average_buy_price", "0"))))
    return Position(
        symbol=str(raw.get("symbol", "")),
        quantity=quantity,
        average_cost=average_cost,
        cost_basis=quantity * average_cost,
    )


def _extract_cash(portfolio: dict) -> tuple[Decimal, Decimal]:
    data = portfolio.get("data") if isinstance(portfolio.get("data"), dict) else portfolio

    def dec(*keys: str) -> Decimal:
        for k in keys:
            value = data.get(k)
            if value is not None:
                return Decimal(str(value))
        return Decimal("0")

    cash = dec("cash", "uninvested_cash", "cash_available_for_withdrawal")
    buying_power = dec("buying_power", "equity_buying_power")
    return cash, buying_power


def reconcile(broker, settings) -> PortfolioState:
    account = select_account(broker.get_accounts(), settings.account_number)
    account_number = str(account["account_number"])
    positions = [_to_position(p) for p in broker.get_equity_positions(account_number)]
    cash, buying_power = _extract_cash(broker.get_portfolio(account_number))
    return PortfolioState(
        account_number=account_number,
        positions=positions,
        cash=cash,
        buying_power=buying_power,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_reconcile.py -v`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/memory/portfolio.py tests/unit/test_reconcile.py
git commit -m "feat: reconcile live broker state into PortfolioState"
```

---

### Task 10: Quote enrichment — `enrich_with_quotes()`

Add current price, market value, and unrealized P/L per position, plus aggregate market value / total value / total return. **Best-effort:** if a quote is missing, that position keeps `None` enrichment fields and is excluded from the aggregates — reconciliation never fails because a quote is unavailable.

> **Shape note:** quote price field names are assumed; confirmed in **Task 15**.

**Files:**
- Modify: `src/rh_wizard/memory/portfolio.py`
- Create: `tests/unit/test_enrich.py`

**Interfaces:**
- Consumes: `BrokerClient.get_equity_quotes` (Task 7), `PortfolioState`/`Position` (Task 5).
- Produces (in `memory/portfolio.py`):
  - `enrich_with_quotes(state: PortfolioState, broker) -> PortfolioState`
  - helper `_quote_price(quote: dict) -> Decimal | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_enrich.py
from decimal import Decimal

from rh_wizard.memory.portfolio import enrich_with_quotes
from rh_wizard.models.portfolio import PortfolioState, Position


def _state():
    return PortfolioState(
        account_number="ACC1",
        positions=[
            Position(
                symbol="AAPL",
                quantity=Decimal("10"),
                average_cost=Decimal("100"),
                cost_basis=Decimal("1000"),
            )
        ],
        cash=Decimal("500"),
        buying_power=Decimal("500"),
    )


class FakeBroker:
    def __init__(self, quotes):
        self._quotes = quotes

    def get_equity_quotes(self, symbols):
        return self._quotes


def test_enrich_adds_market_value_and_return():
    broker = FakeBroker([{"symbol": "AAPL", "last_trade_price": "120.00"}])
    out = enrich_with_quotes(_state(), broker)
    pos = out.positions[0]
    assert pos.current_price == Decimal("120.00")
    assert pos.market_value == Decimal("1200.00")
    assert pos.unrealized_pl == Decimal("200.00")
    assert pos.unrealized_pl_pct == Decimal("20")
    assert out.market_value == Decimal("1200.00")
    assert out.total_value == Decimal("1700.00")
    assert out.total_return_pct == Decimal("20")


def test_enrich_degrades_when_quote_missing():
    broker = FakeBroker([])  # no quote for AAPL
    out = enrich_with_quotes(_state(), broker)
    assert out.positions[0].current_price is None
    assert out.market_value is None
    assert out.total_value is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_enrich.py -v`
Expected: FAIL with `ImportError: cannot import name 'enrich_with_quotes'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/rh_wizard/memory/portfolio.py`:

```python
def _quote_price(quote: dict) -> Decimal | None:
    for key in ("last_trade_price", "price", "last_price", "mark_price"):
        value = quote.get(key)
        if value is not None:
            return Decimal(str(value))
    return None


def enrich_with_quotes(state: PortfolioState, broker) -> PortfolioState:
    symbols = [p.symbol for p in state.positions if p.symbol]
    if not symbols:
        return state
    quotes = {q.get("symbol"): q for q in broker.get_equity_quotes(symbols)}

    enriched: list[Position] = []
    total_mv = Decimal("0")
    total_cb = Decimal("0")
    for p in state.positions:
        quote = quotes.get(p.symbol)
        price = _quote_price(quote) if quote else None
        if price is None:
            enriched.append(p)
            continue
        market_value = p.quantity * price
        unrealized_pl = market_value - p.cost_basis
        unrealized_pl_pct = (
            unrealized_pl / p.cost_basis * 100 if p.cost_basis else None
        )
        total_mv += market_value
        total_cb += p.cost_basis
        enriched.append(
            p.model_copy(
                update={
                    "current_price": price,
                    "market_value": market_value,
                    "unrealized_pl": unrealized_pl,
                    "unrealized_pl_pct": unrealized_pl_pct,
                }
            )
        )

    market_value = total_mv if total_mv else None
    total_value = market_value + state.cash if market_value is not None else None
    total_return_pct = (total_mv - total_cb) / total_cb * 100 if total_cb else None
    return state.model_copy(
        update={
            "positions": enriched,
            "market_value": market_value,
            "total_value": total_value,
            "total_return_pct": total_return_pct,
        }
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_enrich.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/memory/portfolio.py tests/unit/test_enrich.py
git commit -m "feat: enrich PortfolioState with quotes (market value, return)"
```

---

### Task 11: `wizard positions` command (+ `render_positions`)

Wire reconcile → enrich → render into a CLI command. The render function and the command ship together (a reviewer evaluates them as one deliverable).

**Files:**
- Modify: `src/rh_wizard/cli/render.py`
- Create: `src/rh_wizard/cli/portfolio.py`
- Modify: `src/rh_wizard/cli/app.py`
- Create: `tests/unit/test_cli_portfolio.py`

**Interfaces:**
- Consumes: `reconcile`, `enrich_with_quotes` (Tasks 9–10), `render_to_str`/`mask_account`/`fmt_*` (Tasks 3–4), `auth._build_broker` (Phase 0), `load_settings` (Phase 0).
- Produces:
  - `render_positions(state: PortfolioState) -> str` (in `cli/render.py`)
  - `run_positions() -> None` (in `cli/portfolio.py`)
  - `wizard positions` command (in `cli/app.py`).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_cli_portfolio.py
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
        return [{"account_number": "ACC123456", "type": "agentic"}]

    def get_equity_positions(self, account_number):
        return [{"symbol": "AAPL", "quantity": "10", "average_cost": "100"}]

    def get_portfolio(self, account_number):
        return {"data": {"cash": "500.00", "buying_power": "500.00"}}

    def get_equity_quotes(self, symbols):
        return [{"symbol": "AAPL", "last_trade_price": "120.00"}]


def test_positions_command_renders_and_masks(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))  # isolate from real config
    monkeypatch.setattr(auth, "_build_broker", lambda settings: FakeBroker())
    result = runner.invoke(app, ["positions"])
    assert result.exit_code == 0
    assert "AAPL" in result.output
    assert "$1,200.00" in result.output  # enriched market value
    assert "ACC123456" not in result.output  # account number masked
    assert "*****3456" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli_portfolio.py -v`
Expected: FAIL with a `typer` "No such command 'positions'" error (exit code 2).

- [ ] **Step 3: Add `render_positions`**

Append to `src/rh_wizard/cli/render.py`:

```python
def render_positions(state) -> str:
    """Render a PortfolioState as a table plus a summary line."""
    from rich.table import Table

    table = Table(title=f"Positions — account {mask_account(state.account_number)}")
    table.add_column("Symbol")
    table.add_column("Qty", justify="right")
    table.add_column("Avg Cost", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Mkt Value", justify="right")
    table.add_column("Unrealized P/L", justify="right")
    table.add_column("%", justify="right")
    for p in state.positions:
        table.add_row(
            p.symbol,
            fmt_num(p.quantity),
            fmt_money(p.average_cost),
            fmt_money(p.current_price),
            fmt_money(p.market_value),
            fmt_money(p.unrealized_pl),
            fmt_pct(p.unrealized_pl_pct),
        )
    summary = (
        f"Cash: {fmt_money(state.cash)}   "
        f"Buying power: {fmt_money(state.buying_power)}   "
        f"Total value: {fmt_money(state.total_value)}   "
        f"Total return: {fmt_pct(state.total_return_pct)}"
    )
    body = render_to_str(table) if state.positions else "No open positions.\n"
    return body + summary
```

- [ ] **Step 4: Create the command runner**

```python
# src/rh_wizard/cli/portfolio.py
"""`wizard positions` and `wizard history` commands."""

from __future__ import annotations

import typer

from rh_wizard.cli import auth
from rh_wizard.cli.render import render_positions
from rh_wizard.config.settings import load_settings
from rh_wizard.memory.portfolio import enrich_with_quotes, reconcile


def run_positions() -> None:
    settings = load_settings()
    broker = auth._build_broker(settings)
    with broker:
        state = reconcile(broker, settings)
        state = enrich_with_quotes(state, broker)
    typer.echo(render_positions(state))
```

- [ ] **Step 5: Register the command**

In `src/rh_wizard/cli/app.py`, add the import and a command. Add near the other imports:

```python
from rh_wizard.cli.portfolio import run_positions
```

Add after the existing `accounts` command:

```python
@app.command()
def positions() -> None:
    """Reconcile live broker state and show current holdings."""
    run_positions()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_cli_portfolio.py -v`
Expected: PASS.

- [ ] **Step 7: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/cli/render.py src/rh_wizard/cli/portfolio.py src/rh_wizard/cli/app.py tests/unit/test_cli_portfolio.py
git commit -m "feat: add wizard positions command"
```

---

### Task 12: `TradeRecord` model + `SqliteJournal`

The persistence layer. `TradeRecord` is the journal's read/write model; `SqliteJournal` stores trades keyed by broker `order_id` (idempotent upsert) and reads them back newest-first. Money/quantities are stored as TEXT to preserve `Decimal` exactness.

> The §6 `Journal` protocol also lists `record_run`/`record_plan`/`record_order`; those reference execution types that do not exist until Phase 5. Phase 1 implements only the trade-history surface the spec scopes here ("Journal (read-only)").

**Files:**
- Create: `src/rh_wizard/models/trade.py`
- Create: `tests/unit/test_models_trade.py`
- Create: `src/rh_wizard/memory/journal.py`
- Create: `tests/unit/test_journal.py`

**Interfaces:**
- Consumes: nothing (model + sqlite stdlib).
- Produces:
  - `TradeRecord(order_id: str, symbol: str, side: str, quantity: Decimal, price: Decimal | None, state: str, created_at: str, source: str | None = None)`
  - `class SqliteJournal` with `__init__(self, path)`, `record_trades(self, trades: list[TradeRecord]) -> int`, `recent_trades(self, limit: int = 50) -> list[TradeRecord]`, `close(self) -> None`, and context-manager support (`__enter__`/`__exit__`).

- [ ] **Step 1: Write the failing model test**

```python
# tests/unit/test_models_trade.py
from decimal import Decimal

from rh_wizard.models.trade import TradeRecord


def test_trade_record_coerces_decimals():
    t = TradeRecord(
        order_id="O1",
        symbol="AAPL",
        side="buy",
        quantity="2",
        price="100.50",
        state="filled",
        created_at="2026-01-01T00:00:00Z",
    )
    assert t.quantity == Decimal("2")
    assert t.price == Decimal("100.50")
    assert t.source is None


def test_trade_record_allows_null_price():
    t = TradeRecord(
        order_id="O2",
        symbol="MSFT",
        side="sell",
        quantity="1",
        price=None,
        state="cancelled",
        created_at="2026-01-02",
    )
    assert t.price is None
```

- [ ] **Step 2: Run model test to verify it fails**

Run: `uv run pytest tests/unit/test_models_trade.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rh_wizard.models.trade'`.

- [ ] **Step 3: Write the model**

```python
# src/rh_wizard/models/trade.py
"""Journal trade record (spec §6/§7). One row per known broker order."""

from __future__ import annotations

from decimal import Decimal

import pydantic


class TradeRecord(pydantic.BaseModel):
    order_id: str  # broker order id — idempotency key
    symbol: str
    side: str  # "buy" / "sell"
    quantity: Decimal
    price: Decimal | None  # avg fill price; None when not (yet) filled
    state: str  # filled / cancelled / rejected / ...
    created_at: str  # ISO timestamp from the broker
    source: str | None = None  # placed_agent: user / agentic / recurring / ...
```

- [ ] **Step 4: Run model test to verify it passes**

Run: `uv run pytest tests/unit/test_models_trade.py -v`
Expected: PASS.

- [ ] **Step 5: Write the failing journal test**

```python
# tests/unit/test_journal.py
from decimal import Decimal

from rh_wizard.memory.journal import SqliteJournal
from rh_wizard.models.trade import TradeRecord


def _trade(order_id="O1", state="filled"):
    return TradeRecord(
        order_id=order_id,
        symbol="AAPL",
        side="buy",
        quantity=Decimal("2"),
        price=Decimal("100"),
        state=state,
        created_at="2026-01-01T00:00:00Z",
        source="agentic",
    )


def test_record_and_read_back(tmp_path):
    with SqliteJournal(tmp_path / "wizard.db") as journal:
        journal.record_trades([_trade()])
        trades = journal.recent_trades()
    assert len(trades) == 1
    assert trades[0].order_id == "O1"
    assert trades[0].quantity == Decimal("2")
    assert trades[0].price == Decimal("100")


def test_upsert_is_idempotent(tmp_path):
    with SqliteJournal(tmp_path / "wizard.db") as journal:
        journal.record_trades([_trade(state="confirmed")])
        journal.record_trades([_trade(state="filled")])  # same order_id, new state
        trades = journal.recent_trades()
    assert len(trades) == 1  # one row, not two
    assert trades[0].state == "filled"  # updated in place


def test_recent_trades_orders_newest_first(tmp_path):
    older = TradeRecord(
        order_id="OLD", symbol="A", side="buy", quantity=Decimal("1"),
        price=None, state="filled", created_at="2026-01-01",
    )
    newer = TradeRecord(
        order_id="NEW", symbol="B", side="buy", quantity=Decimal("1"),
        price=None, state="filled", created_at="2026-02-01",
    )
    with SqliteJournal(tmp_path / "wizard.db") as journal:
        journal.record_trades([older, newer])
        trades = journal.recent_trades()
    assert [t.order_id for t in trades] == ["NEW", "OLD"]
```

- [ ] **Step 6: Run journal test to verify it fails**

Run: `uv run pytest tests/unit/test_journal.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rh_wizard.memory.journal'`.

- [ ] **Step 7: Write the journal**

```python
# src/rh_wizard/memory/journal.py
"""SQLite-backed trade journal (spec §6).

Stores one row per known broker order, keyed by order_id (idempotent upsert). Decimal
fields are stored as TEXT to avoid float precision loss.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

from rh_wizard.models.trade import TradeRecord

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
"""

_UPSERT = """
INSERT INTO trades (order_id, symbol, side, quantity, price, state, created_at, source)
VALUES (:order_id, :symbol, :side, :quantity, :price, :state, :created_at, :source)
ON CONFLICT(order_id) DO UPDATE SET
    state = excluded.state,
    price = excluded.price,
    quantity = excluded.quantity;
"""


class SqliteJournal:
    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def __enter__(self) -> SqliteJournal:
        return self

    def __exit__(self, *exc) -> bool:
        self.close()
        return False

    def record_trades(self, trades: list[TradeRecord]) -> int:
        rows = [
            {
                "order_id": t.order_id,
                "symbol": t.symbol,
                "side": t.side,
                "quantity": str(t.quantity),
                "price": None if t.price is None else str(t.price),
                "state": t.state,
                "created_at": t.created_at,
                "source": t.source,
            }
            for t in trades
        ]
        self._conn.executemany(_UPSERT, rows)
        self._conn.commit()
        return len(rows)

    def recent_trades(self, limit: int = 50) -> list[TradeRecord]:
        cur = self._conn.execute(
            "SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [_row_to_trade(row) for row in cur.fetchall()]

    def close(self) -> None:
        self._conn.close()


def _row_to_trade(row: sqlite3.Row) -> TradeRecord:
    return TradeRecord(
        order_id=row["order_id"],
        symbol=row["symbol"],
        side=row["side"],
        quantity=Decimal(row["quantity"]),
        price=None if row["price"] is None else Decimal(row["price"]),
        state=row["state"],
        created_at=row["created_at"],
        source=row["source"],
    )
```

- [ ] **Step 8: Run journal test to verify it passes**

Run: `uv run pytest tests/unit/test_journal.py tests/unit/test_models_trade.py -v`
Expected: PASS.

- [ ] **Step 9: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/models/trade.py tests/unit/test_models_trade.py src/rh_wizard/memory/journal.py tests/unit/test_journal.py
git commit -m "feat: add TradeRecord model and SqliteJournal"
```

---

### Task 13: Order sync — `sync_equity_orders()`

Bridge the broker's order history into the journal: fetch equity orders, map each to a `TradeRecord`, upsert. This is what makes `wizard history` SQLite-backed and accumulating; the same recording path is reused when our own executions land in later phases.

> **Shape note:** order field names (`id`, `side`, `quantity`, `average_price`, `placed_agent`) are assumed; confirmed in **Task 15**.

**Files:**
- Create: `src/rh_wizard/memory/sync.py`
- Create: `tests/unit/test_sync.py`

**Interfaces:**
- Consumes: `BrokerClient.get_equity_orders` (Task 7), `SqliteJournal.record_trades` (Task 12), `TradeRecord` (Task 12).
- Produces (in `memory/sync.py`):
  - `sync_equity_orders(broker, account_number: str, journal, *, created_at_gte: str | None = None) -> int`
  - helpers `_to_trade_record(raw: dict) -> TradeRecord`, `_order_price(raw: dict) -> Decimal | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_sync.py
from decimal import Decimal

from rh_wizard.memory.journal import SqliteJournal
from rh_wizard.memory.sync import sync_equity_orders


class FakeBroker:
    def __init__(self, orders):
        self._orders = orders
        self.last_kwargs = None

    def get_equity_orders(self, account_number, *, created_at_gte=None):
        self.last_kwargs = {"account_number": account_number, "created_at_gte": created_at_gte}
        return self._orders


def test_sync_writes_orders_to_journal(tmp_path):
    broker = FakeBroker(
        [
            {
                "id": "O1",
                "symbol": "AAPL",
                "side": "buy",
                "quantity": "2",
                "average_price": "100",
                "state": "filled",
                "created_at": "2026-01-01",
                "placed_agent": "agentic",
            }
        ]
    )
    with SqliteJournal(tmp_path / "wizard.db") as journal:
        count = sync_equity_orders(broker, "ACC1", journal, created_at_gte="2026-01-01")
        trades = journal.recent_trades()
    assert count == 1
    assert broker.last_kwargs == {"account_number": "ACC1", "created_at_gte": "2026-01-01"}
    assert trades[0].order_id == "O1"
    assert trades[0].symbol == "AAPL"
    assert trades[0].price == Decimal("100")
    assert trades[0].source == "agentic"


def test_sync_is_idempotent(tmp_path):
    order = {
        "id": "O1", "symbol": "AAPL", "side": "buy", "quantity": "2",
        "average_price": "100", "state": "filled", "created_at": "2026-01-01",
    }
    broker = FakeBroker([order])
    with SqliteJournal(tmp_path / "wizard.db") as journal:
        sync_equity_orders(broker, "ACC1", journal)
        sync_equity_orders(broker, "ACC1", journal)
        trades = journal.recent_trades()
    assert len(trades) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_sync.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rh_wizard.memory.sync'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/rh_wizard/memory/sync.py
"""Sync the broker's equity order history into the journal (idempotent)."""

from __future__ import annotations

from decimal import Decimal

from rh_wizard.models.trade import TradeRecord


def _order_price(raw: dict) -> Decimal | None:
    for key in ("average_price", "price", "last_trade_price"):
        value = raw.get(key)
        if value is not None:
            return Decimal(str(value))
    return None


def _to_trade_record(raw: dict) -> TradeRecord:
    return TradeRecord(
        order_id=str(raw.get("id") or raw.get("order_id") or ""),
        symbol=str(raw.get("symbol", "")),
        side=str(raw.get("side", "")),
        quantity=Decimal(str(raw.get("quantity", raw.get("shares", "0")))),
        price=_order_price(raw),
        state=str(raw.get("state", "")),
        created_at=str(raw.get("created_at", "")),
        source=raw.get("placed_agent") or raw.get("source"),
    )


def sync_equity_orders(
    broker, account_number: str, journal, *, created_at_gte: str | None = None
) -> int:
    raw_orders = broker.get_equity_orders(account_number, created_at_gte=created_at_gte)
    records = [_to_trade_record(o) for o in raw_orders]
    return journal.record_trades(records)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_sync.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/memory/sync.py tests/unit/test_sync.py
git commit -m "feat: sync broker equity order history into the journal"
```

---

### Task 14: `wizard history` command (+ `render_history`)

Wire account resolution → order sync → journal read → render into a CLI command, persisting to the real SQLite db under `RH_WIZARD_HOME`.

**Files:**
- Modify: `src/rh_wizard/cli/render.py`
- Modify: `src/rh_wizard/cli/portfolio.py`
- Modify: `src/rh_wizard/cli/app.py`
- Create: `tests/unit/test_cli_history.py`

**Interfaces:**
- Consumes: `resolve_account_number` (Task 8), `sync_equity_orders` (Task 13), `SqliteJournal` (Task 12), `paths.db_path`/`paths.ensure_home` (Phase 0), `render_to_str`/`fmt_*` (Task 4).
- Produces:
  - `render_history(trades: list[TradeRecord]) -> str` (in `cli/render.py`)
  - `run_history(limit: int = 50, since: str | None = None) -> None` (in `cli/portfolio.py`)
  - `wizard history` command (in `cli/app.py`).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_cli_history.py
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
        return [{"account_number": "ACC123456", "type": "agentic"}]

    def get_equity_orders(self, account_number, *, created_at_gte=None):
        return [
            {
                "id": "O1",
                "symbol": "AAPL",
                "side": "buy",
                "quantity": "2",
                "average_price": "100",
                "state": "filled",
                "created_at": "2026-01-01",
                "placed_agent": "agentic",
            }
        ]


def test_history_command_persists_and_renders(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))
    monkeypatch.setattr(auth, "_build_broker", lambda settings: FakeBroker())

    result = runner.invoke(app, ["history"])
    assert result.exit_code == 0
    assert "AAPL" in result.output
    assert (tmp_path / "wizard.db").exists()

    # Re-running is idempotent and still renders.
    result2 = runner.invoke(app, ["history"])
    assert result2.exit_code == 0
    assert "AAPL" in result2.output


def test_history_command_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))

    class EmptyBroker(FakeBroker):
        def get_equity_orders(self, account_number, *, created_at_gte=None):
            return []

    monkeypatch.setattr(auth, "_build_broker", lambda settings: EmptyBroker())
    result = runner.invoke(app, ["history"])
    assert result.exit_code == 0
    assert "No order history yet." in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli_history.py -v`
Expected: FAIL with a `typer` "No such command 'history'" error (exit code 2).

- [ ] **Step 3: Add `render_history`**

Append to `src/rh_wizard/cli/render.py`:

```python
def render_history(trades) -> str:
    """Render a list of TradeRecords as a table (newest first)."""
    if not trades:
        return "No order history yet."

    from rich.table import Table

    table = Table(title="Order history")
    table.add_column("Date")
    table.add_column("Symbol")
    table.add_column("Side")
    table.add_column("Qty", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("State")
    table.add_column("Source")
    for t in trades:
        table.add_row(
            t.created_at,
            t.symbol,
            t.side,
            fmt_num(t.quantity),
            fmt_money(t.price),
            t.state,
            t.source or "-",
        )
    return render_to_str(table)
```

- [ ] **Step 4: Add `run_history`**

In `src/rh_wizard/cli/portfolio.py`, extend the imports and add the runner. Replace the import block at the top with:

```python
from __future__ import annotations

import typer

from rh_wizard.cli import auth
from rh_wizard.cli.render import render_history, render_positions
from rh_wizard.config import paths
from rh_wizard.config.settings import load_settings
from rh_wizard.memory.journal import SqliteJournal
from rh_wizard.memory.portfolio import enrich_with_quotes, reconcile, resolve_account_number
from rh_wizard.memory.sync import sync_equity_orders
```

Append the runner:

```python
def run_history(limit: int = 50, since: str | None = None) -> None:
    paths.ensure_home()
    settings = load_settings()
    broker = auth._build_broker(settings)
    with broker:
        account_number = resolve_account_number(broker, settings)
        with SqliteJournal(paths.db_path()) as journal:
            sync_equity_orders(broker, account_number, journal, created_at_gte=since)
            trades = journal.recent_trades(limit)
    typer.echo(render_history(trades))
```

- [ ] **Step 5: Register the command**

In `src/rh_wizard/cli/app.py`, update the portfolio import and add the command. Change the import line to:

```python
from rh_wizard.cli.portfolio import run_history, run_positions
```

Add after the `positions` command:

```python
@app.command()
def history(
    limit: int = typer.Option(50, help="Max number of orders to show."),
    since: str = typer.Option(None, help="Only sync orders on/after this date (YYYY-MM-DD)."),
) -> None:
    """Sync broker order history into the journal and show recent trades."""
    run_history(limit, since)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_cli_history.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Lint + commit**

Run: `uv run ruff check . && uv run ruff format --check .`

```bash
git add src/rh_wizard/cli/render.py src/rh_wizard/cli/portfolio.py src/rh_wizard/cli/app.py tests/unit/test_cli_history.py
git commit -m "feat: add wizard history command"
```

---

### Task 15: Live shape verification + README + final gate

Phase 0's pattern (§18): write thin defensive parsers, then verify against the real server and pin the confirmed shapes. This task adds the env-gated live test, documents the new commands, and records confirmed field names.

**Files:**
- Create: `tests/integration/test_live_portfolio.py`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-06-21-robinhood-wizard-design.md` (record confirmed shapes)

**Interfaces:**
- Consumes: `reconcile`, `enrich_with_quotes`, `resolve_account_number`, `sync_equity_orders`, `SqliteJournal`, `load_settings`, `auth._build_broker`.
- Produces: a live, opt-in verification path.

- [ ] **Step 1: Write the live integration test**

```python
# tests/integration/test_live_portfolio.py
"""Live, opt-in shape verification against the real Robinhood MCP (read-only).

Run explicitly (needs a cached token from `wizard auth login`):
    RH_WIZARD_LIVE=1 uv run pytest tests/integration/test_live_portfolio.py -v -s

Prints the reconciled portfolio and synced history so the assumed payload field names in
the broker/reconcile/sync parsers can be confirmed (see spec §18).
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RH_WIZARD_LIVE") != "1",
    reason="set RH_WIZARD_LIVE=1 to run the live portfolio test",
)


def test_reconcile_and_history_live(tmp_path):
    from rh_wizard.cli import auth
    from rh_wizard.config.settings import load_settings
    from rh_wizard.memory.journal import SqliteJournal
    from rh_wizard.memory.portfolio import (
        enrich_with_quotes,
        reconcile,
        resolve_account_number,
    )
    from rh_wizard.memory.sync import sync_equity_orders

    settings = load_settings()
    broker = auth._build_broker(settings)
    with broker:
        state = enrich_with_quotes(reconcile(broker, settings), broker)
        account_number = resolve_account_number(broker, settings)
        with SqliteJournal(tmp_path / "wizard.db") as journal:
            synced = sync_equity_orders(broker, account_number, journal)
            trades = journal.recent_trades()

    print("\nPortfolioState:", state.model_dump())
    print("Synced orders:", synced)
    print("Recent trades:", [t.model_dump() for t in trades])

    assert state.account_number
    assert isinstance(state.positions, list)
    assert isinstance(trades, list)
```

- [ ] **Step 2: Verify it skips without the env flag**

Run: `uv run pytest tests/integration/test_live_portfolio.py -v`
Expected: SKIPPED (1 skipped), reason "set RH_WIZARD_LIVE=1...".

- [ ] **Step 3: Run the live verification (manual, requires a real account)**

Run: `RH_WIZARD_LIVE=1 uv run pytest tests/integration/test_live_portfolio.py -v -s`
Expected: PASS, and the printed `PortfolioState` / trades show real, non-empty fields (symbols, quantities, cash, prices).

If any field comes back empty/wrong, the assumed key names need adjusting in:
- `broker/client.py` `_extract_list` / `_next_cursor` (positions/orders nesting + `next`/`cursor`),
- `memory/portfolio.py` `_to_position` / `_extract_cash` / `_quote_price` / `_is_agentic`,
- `memory/sync.py` `_to_trade_record` / `_order_price`.

Fix the key names, re-run the relevant unit tests (update their fixtures to match the confirmed shape), and re-run this live test until green.

- [ ] **Step 4: Record confirmed shapes in the spec**

In `docs/superpowers/specs/2026-06-21-robinhood-wizard-design.md`, append to §18 a Phase 1 entry noting the confirmed payload shapes (e.g. "positions nest under `data.results`; price field is `last_trade_price`; agentic accounts carry `brokerage_account_type = 'agentic'`"). Mirror the existing "RESOLVED" style.

- [ ] **Step 5: Document the new commands in the README**

Add a "Usage (Phase 1)" section to `README.md`:

```markdown
## Usage

After `wizard auth login`:

- `wizard positions` — reconcile live broker state and show current holdings
  (quantity, average cost, current price, market value, unrealized P/L), plus cash,
  buying power, and total return.
- `wizard history [--limit N] [--since YYYY-MM-DD]` — sync your equity order history
  into the local journal (`~/.rh-wizard/wizard.db`) and show recent trades.

All output masks account numbers to the last 4 characters. These commands are read-only —
no orders are placed or cancelled.
```

- [ ] **Step 6: Full-suite gate**

Run: `uv run pytest && uv run ruff check . && uv run ruff format --check .`
Expected: ALL PASS (unit tests green; the live integration test SKIPPED without the env flag), ruff clean.

- [ ] **Step 7: Commit**

```bash
git add tests/integration/test_live_portfolio.py README.md docs/superpowers/specs/2026-06-21-robinhood-wizard-design.md
git commit -m "test: add live portfolio/history shape verification; document Phase 1 usage"
```

- [ ] **Step 8: Open the PR**

```bash
git push -u origin phase-1
gh pr create --title "Phase 1: read-only broker, reconciliation, PortfolioState, SQLite journal" \
  --body "Implements spec §17 Phase 1: broker read wrappers, reconcile -> PortfolioState, SqliteJournal, wizard positions/history. Clears §18 cleanups (mask account numbers, silence session-termination warning, remove unused OAuthCallbackServer)."
```

---

## Out of Scope (Phase 1)

Deferred to later phases — do **not** build here:
- **Risk engine / `RiskPolicy`** (Phase 2).
- **`PerformanceTracker`, high-water mark, kill-switch** (spec §8 step 4; Phase 6). `total_return_pct` here is a display field only — no persistence, no drawdown logic.
- **Data layer / `SignalResolver`, research agent, plan generator** (Phases 3–4).
- **Order placement / `review`+`place`, `ApprovalGate`, execution modes** (Phase 5). Phase 1 is strictly read-only.
- **`Journal.record_run`/`record_plan`/`record_order`** for cycle artifacts (arrive with the execution pipeline, Phase 4–5).
```