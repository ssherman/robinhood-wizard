# Robinhood Wizard — Phase 0 (Scaffold & Auth) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the project skeleton (uv + ruff + pytest + CI + MIT/OSS files) and prove a headless Python process can authenticate to the Robinhood Agentic Trading MCP server via OAuth 2.1 and silently refresh its token to list accounts.

**Architecture:** A deterministic safety-first foundation. All offline-testable logic (config, paths, secret redaction, token persistence, the OAuth localhost callback, CLI wiring) is built TDD-first behind clean seams and mocked at the external-SDK boundary. The one genuinely interactive, network-dependent piece — the live OAuth consent + MCP connection — is isolated into a single env-gated integration task that resolves the unknowns flagged in spec §18.

**Tech Stack:** Python 3.12, uv, ruff, pytest, Typer (CLI), Pydantic v2, PyYAML, the `mcp` Python SDK (OAuth client + Streamable HTTP transport), Strands Agents SDK (`MCPClient`), httpx.

## Global Constraints

_Every task's requirements implicitly include this section. Values copied verbatim from the spec._

- **Python 3.12.** Deps via **uv** (`pyproject.toml` + `uv.lock`). Lint/format **ruff**. Tests **pytest**.
- **License: MIT** (`LICENSE` at repo root).
- **Secrets hygiene (critical):** OAuth tokens, the SQLite DB, and any `.env` are gitignored and **never committed**. Config and runtime state live in `~/.rh-wizard/`, never in the repo. Committed example files (`config.example.yaml`, `.env.example`) contain placeholders only. **No credentials, account numbers, or PII are ever logged** — the audit log/journal must be safe to share. A test asserts logs contain no secret-shaped values.
- **Financial/legal disclaimer (mandatory):** prominent notice in `README` and on first CLI run — *not financial advice, no warranty, use at your own risk, authors not liable for losses.*
- **No personal config baked in:** no hardcoded strategies, account specifics, or author-specific defaults.
- **Provider-agnostic model config:** model provider/id is configurable, never hardcoded.
- **Robinhood MCP:** endpoint `https://agent.robinhood.com/mcp/trading`, **Streamable HTTP** transport, **OAuth 2.1** (authorization-code + PKCE + dynamic client registration); access tokens ~4 days, refresh token enables silent renewal.
- **Open risks to verify hands-on (spec §18):** `mcp` API signature drift (`streamablehttp_client(headers=, auth=)` vs `streamable_http_client(http_client=...)`); whether `OAuthClientProvider` `server_url` is the base host or the full `/mcp/trading` path; DCR with `token_endpoint_auth_method: none` from a non-Claude client (claude-code #65895). These are resolved in **Task 9**, not assumed earlier.

---

## File Structure

```
robinhood-wizard/
  pyproject.toml                      # Task 0 — uv project, deps, ruff + pytest config, `wizard` script
  uv.lock                             # Task 0
  .github/workflows/ci.yml            # Task 0 — ruff + pytest on push/PR
  LICENSE                             # Task 1 — MIT
  README.md                           # Task 1 — overview, disclaimer, setup
  CONTRIBUTING.md                     # Task 1
  SECURITY.md                         # Task 1
  .env.example                        # Task 1 — placeholders only
  config.example.yaml                 # Task 1 — placeholders only
  src/rh_wizard/
    __init__.py                       # Task 0
    config/
      __init__.py
      paths.py                        # Task 2 — ~/.rh-wizard path resolution (env-overridable)
      settings.py                     # Task 3 — Settings model + load_settings()
    logging/
      __init__.py
      redaction.py                    # Task 4 — secret-scrubbing log filter
    auth/
      __init__.py
      token_storage.py                # Task 5 — TokenFile (TDD core) + DiskTokenStorage (MCP adapter)
      callback.py                     # Task 6 — localhost OAuth redirect catcher (TDD)
      oauth.py                        # Task 7 — build_oauth_provider() wiring
    broker/
      __init__.py
      client.py                       # Task 8 — make_broker_client(), get_accounts()
    cli/
      __init__.py
      app.py                          # Task 0 smoke / Task 9 wiring — Typer app + disclaimer
      auth.py                         # Task 9 — `wizard auth login`, `wizard accounts`
  tests/
    unit/
      test_paths.py                   # Task 2
      test_settings.py                # Task 3
      test_redaction.py               # Task 4
      test_token_storage.py           # Task 5
      test_callback.py                # Task 6
      test_oauth.py                   # Task 7
      test_broker_client.py           # Task 8
      test_cli_auth.py                # Task 9
    integration/
      test_live_auth.py               # Task 9b — env-gated, manual browser
```

---

### Task 0: Project scaffold, tooling, and CI

**Files:**
- Create: `pyproject.toml`, `uv.lock`, `src/rh_wizard/__init__.py`, `.github/workflows/ci.yml`
- Create: `tests/unit/test_smoke.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `rh_wizard.__version__: str`; a working `uv run pytest` and `uv run ruff check`; the package import root `rh_wizard`.

- [ ] **Step 1: Initialize the uv project**

Run (creates `pyproject.toml` + `src/rh_wizard/` + `uv.lock`):

```bash
uv init --package --name rh-wizard --python 3.12 .
```

If `uv init` refuses because the directory is non-empty, create `pyproject.toml` by hand from Step 3 and run `uv sync` instead.

- [ ] **Step 2: Add runtime and dev dependencies**

```bash
uv add strands-agents "mcp>=1.28,<2" "pydantic>=2.7" "typer>=0.12" "httpx>=0.27" "pyyaml>=6.0"
uv add --dev "pytest>=8" "pytest-cov>=5" "ruff>=0.6"
```

- [ ] **Step 3: Set the final `pyproject.toml` config**

Ensure `pyproject.toml` contains (merge with what `uv` generated; keep `uv`'s resolved dependency versions):

```toml
[project]
name = "rh-wizard"
version = "0.1.0"
description = "AI-powered stock-trading agent framework (Robinhood Wizard)"
readme = "README.md"
requires-python = ">=3.12"
license = { text = "MIT" }
# dependencies = [...]  # left as resolved by `uv add`

[project.scripts]
wizard = "rh_wizard.cli.app:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/rh_wizard"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
addopts = "-q"
```

- [ ] **Step 4: Set the package version export**

Write `src/rh_wizard/__init__.py`:

```python
"""Robinhood Wizard — AI-powered stock-trading agent framework."""

__version__ = "0.1.0"
```

- [ ] **Step 5: Write the smoke test**

Write `tests/unit/test_smoke.py`:

```python
import rh_wizard


def test_package_exposes_version():
    assert rh_wizard.__version__ == "0.1.0"
```

- [ ] **Step 6: Run the smoke test (expect PASS) and lint (expect clean)**

```bash
uv run pytest tests/unit/test_smoke.py -v
uv run ruff check .
```

Expected: 1 passed; ruff reports `All checks passed!`.

- [ ] **Step 7: Add the CI workflow**

Write `.github/workflows/ci.yml`:

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"
      - run: uv sync --all-extras --dev
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run pytest
```

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock src/rh_wizard/__init__.py tests/unit/test_smoke.py .github/workflows/ci.yml
git commit -m "chore: scaffold uv project with ruff, pytest, and CI"
```

---

### Task 1: License, README (with disclaimer), and community files

**Files:**
- Create: `LICENSE`, `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `.env.example`, `config.example.yaml`
- Create: `tests/unit/test_oss_files.py`

**Interfaces:**
- Consumes: nothing.
- Produces: the canonical disclaimer string (reused by the CLI in Task 9): `"DISCLAIMER: Not financial advice. No warranty. Use at your own risk. The authors are not liable for any financial loss."`

- [ ] **Step 1: Write the failing OSS-compliance test**

Write `tests/unit/test_oss_files.py`:

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DISCLAIMER = (
    "DISCLAIMER: Not financial advice. No warranty. Use at your own risk. "
    "The authors are not liable for any financial loss."
)


def test_mit_license_present():
    text = (ROOT / "LICENSE").read_text()
    assert "MIT License" in text
    assert "Permission is hereby granted, free of charge" in text


def test_readme_has_disclaimer():
    assert DISCLAIMER in (ROOT / "README.md").read_text()


def test_example_files_have_no_real_secrets():
    for name in (".env.example", "config.example.yaml"):
        text = (ROOT / name).read_text().lower()
        # placeholders only — never a real Robinhood/agent token value
        assert "agent.robinhood.com" not in text or "your-" in text or "<" in text
        assert "refresh_token" not in text or "your-" in text or "<" in text


def test_security_and_contributing_present():
    assert (ROOT / "SECURITY.md").exists()
    assert (ROOT / "CONTRIBUTING.md").exists()
```

- [ ] **Step 2: Run it to verify it fails**

```bash
uv run pytest tests/unit/test_oss_files.py -v
```

Expected: FAIL (files do not exist yet).

- [ ] **Step 3: Write `LICENSE` (MIT)**

```text
MIT License

Copyright (c) 2026 Shane Sherman

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 4: Write `README.md`**

````markdown
# Robinhood Wizard

An extensible, AI-powered stock-trading agent framework. Describe a strategy in plain
language; the agent researches the market, news, and sentiment, then proposes a trade
plan that runs in DryRun, Human-Approval, or Autonomous mode — always inside
per-strategy guardrails. Equities and ETFs only.

> **DISCLAIMER: Not financial advice. No warranty. Use at your own risk. The authors are not liable for any financial loss.**
> This software can place real trades with real money. You are solely responsible for any use.

## Status

Early development. See `docs/superpowers/specs/` for the design and
`docs/superpowers/plans/` for implementation plans.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- A Robinhood **Agentic Trading** account (opened on desktop) authorized for the agent.

## Setup

```bash
uv sync
cp config.example.yaml ~/.rh-wizard/config.yaml   # then edit
uv run wizard auth login                           # one-time browser consent
uv run wizard accounts                             # verify the connection
```

Tokens and your local database live under `~/.rh-wizard/` and are never committed.

## License

MIT — see [LICENSE](LICENSE).
````

- [ ] **Step 5: Write `CONTRIBUTING.md`**

```markdown
# Contributing

Thanks for your interest! This project trades real money, so correctness and safety
come first.

- Use `uv` for everything: `uv sync`, `uv run pytest`, `uv run ruff check .`.
- TDD: write a failing test first, then the minimal implementation.
- Never commit secrets. Tokens, `.env`, and `*.db` are gitignored — keep it that way.
- New strategies, data sources, and executors should implement the documented
  interfaces (`Strategy`, `DataSource`, `OrderExecutor`, `Journal`).
- Run `uv run ruff format .` before committing.
```

- [ ] **Step 6: Write `SECURITY.md`**

```markdown
# Security Policy

This project handles brokerage credentials and can place trades. If you discover a
vulnerability, please **do not open a public issue**. Email the maintainer at
shane.sherman@gmail.com with details and a reproduction. We aim to respond within 7 days.

Never share your `~/.rh-wizard/tokens.json`, `.env`, or database files — they contain
or derive from live credentials.
```

- [ ] **Step 7: Write `.env.example`**

```bash
# Copy to .env and fill in. NEVER commit your real .env.
# Optional model-provider credentials (provider-agnostic; set what you use):
# ANTHROPIC_API_KEY=your-key-here
# AWS_PROFILE=your-profile
# Override the config/runtime home (defaults to ~/.rh-wizard):
# RH_WIZARD_HOME=/path/to/your/home
```

- [ ] **Step 8: Write `config.example.yaml`**

```yaml
# Copy to ~/.rh-wizard/config.yaml and edit. Placeholders only — no real secrets here.
robinhood_mcp_url: "https://agent.robinhood.com/mcp/trading"

# Provider-agnostic model selection (Strands). Examples:
model_provider: "anthropic"        # or "bedrock", "openai", ...
model_id: "claude-sonnet-4-6"      # your chosen model

# OAuth localhost callback used during `wizard auth login`:
oauth_redirect_host: "localhost"
oauth_redirect_port: 3030
oauth_client_name: "Robinhood Wizard"
```

- [ ] **Step 9: Run the test to verify it passes**

```bash
uv run pytest tests/unit/test_oss_files.py -v
```

Expected: 4 passed.

- [ ] **Step 10: Commit**

```bash
git add LICENSE README.md CONTRIBUTING.md SECURITY.md .env.example config.example.yaml tests/unit/test_oss_files.py
git commit -m "docs: add MIT license, README with disclaimer, and community files"
```

---

### Task 2: Config paths (`config/paths.py`)

**Files:**
- Create: `src/rh_wizard/config/__init__.py`, `src/rh_wizard/config/paths.py`
- Test: `tests/unit/test_paths.py`

**Interfaces:**
- Consumes: env var `RH_WIZARD_HOME` (optional override).
- Produces:
  - `home_dir() -> pathlib.Path` — base dir, `~/.rh-wizard` unless `RH_WIZARD_HOME` set.
  - `config_path() -> pathlib.Path` — `<home>/config.yaml`.
  - `tokens_path() -> pathlib.Path` — `<home>/tokens.json`.
  - `db_path() -> pathlib.Path` — `<home>/wizard.db`.
  - `ensure_home() -> pathlib.Path` — creates `<home>` (mode 0700) and returns it.

- [ ] **Step 1: Write the failing test**

Write `tests/unit/test_paths.py`:

```python
import stat

from rh_wizard.config import paths


def test_home_dir_defaults_to_dot_rh_wizard(monkeypatch):
    monkeypatch.delenv("RH_WIZARD_HOME", raising=False)
    assert paths.home_dir().name == ".rh-wizard"


def test_home_dir_honors_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path / "custom"))
    assert paths.home_dir() == tmp_path / "custom"


def test_derived_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))
    assert paths.config_path() == tmp_path / "config.yaml"
    assert paths.tokens_path() == tmp_path / "tokens.json"
    assert paths.db_path() == tmp_path / "wizard.db"


def test_ensure_home_creates_dir_0700(monkeypatch, tmp_path):
    target = tmp_path / "home"
    monkeypatch.setenv("RH_WIZARD_HOME", str(target))
    result = paths.ensure_home()
    assert result.is_dir()
    assert stat.S_IMODE(result.stat().st_mode) == 0o700
```

- [ ] **Step 2: Run it to verify it fails**

```bash
uv run pytest tests/unit/test_paths.py -v
```

Expected: FAIL with `ModuleNotFoundError: rh_wizard.config.paths`.

- [ ] **Step 3: Create the package marker**

Write `src/rh_wizard/config/__init__.py`:

```python
```

(empty file)

- [ ] **Step 4: Implement `paths.py`**

Write `src/rh_wizard/config/paths.py`:

```python
"""Filesystem locations for Robinhood Wizard runtime state.

All runtime state lives under a single home directory (default ``~/.rh-wizard``),
overridable with the ``RH_WIZARD_HOME`` env var (used by tests and power users).
"""

from __future__ import annotations

import os
from pathlib import Path


def home_dir() -> Path:
    override = os.environ.get("RH_WIZARD_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".rh-wizard"


def config_path() -> Path:
    return home_dir() / "config.yaml"


def tokens_path() -> Path:
    return home_dir() / "tokens.json"


def db_path() -> Path:
    return home_dir() / "wizard.db"


def ensure_home() -> Path:
    d = home_dir()
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    # mkdir's mode is subject to umask; enforce explicitly.
    d.chmod(0o700)
    return d
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
uv run pytest tests/unit/test_paths.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add src/rh_wizard/config/__init__.py src/rh_wizard/config/paths.py tests/unit/test_paths.py
git commit -m "feat: add config path resolution"
```

---

### Task 3: Settings loader (`config/settings.py`)

**Files:**
- Create: `src/rh_wizard/config/settings.py`
- Test: `tests/unit/test_settings.py`

**Interfaces:**
- Consumes: `paths.config_path()` (Task 2); a YAML config file.
- Produces:
  - `class Settings(pydantic.BaseModel)` with fields: `robinhood_mcp_url: str` (default `"https://agent.robinhood.com/mcp/trading"`), `model_provider: str` (default `"anthropic"`), `model_id: str` (default `"claude-sonnet-4-6"`), `oauth_redirect_host: str` (default `"localhost"`), `oauth_redirect_port: int` (default `3030`), `oauth_client_name: str` (default `"Robinhood Wizard"`).
  - `load_settings(path: pathlib.Path | None = None) -> Settings` — loads YAML if present, else all defaults; unknown keys rejected.

- [ ] **Step 1: Write the failing test**

Write `tests/unit/test_settings.py`:

```python
import pytest

from rh_wizard.config.settings import Settings, load_settings


def test_defaults_when_no_file(tmp_path):
    s = load_settings(tmp_path / "missing.yaml")
    assert s.robinhood_mcp_url == "https://agent.robinhood.com/mcp/trading"
    assert s.model_provider == "anthropic"
    assert s.oauth_redirect_port == 3030


def test_file_overrides_defaults(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "model_provider: bedrock\n"
        "model_id: claude-opus-4-8\n"
        "oauth_redirect_port: 4040\n"
    )
    s = load_settings(cfg)
    assert s.model_provider == "bedrock"
    assert s.model_id == "claude-opus-4-8"
    assert s.oauth_redirect_port == 4040
    # untouched fields keep defaults
    assert s.robinhood_mcp_url == "https://agent.robinhood.com/mcp/trading"


def test_unknown_key_rejected(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("bogus_key: 1\n")
    with pytest.raises(ValueError):
        load_settings(cfg)


def test_settings_is_constructible_with_no_args():
    assert isinstance(Settings(), Settings)
```

- [ ] **Step 2: Run it to verify it fails**

```bash
uv run pytest tests/unit/test_settings.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `settings.py`**

Write `src/rh_wizard/config/settings.py`:

```python
"""Global, user-editable configuration (loaded from ``~/.rh-wizard/config.yaml``)."""

from __future__ import annotations

from pathlib import Path

import pydantic
import yaml

from rh_wizard.config import paths


class Settings(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")

    robinhood_mcp_url: str = "https://agent.robinhood.com/mcp/trading"
    model_provider: str = "anthropic"
    model_id: str = "claude-sonnet-4-6"
    oauth_redirect_host: str = "localhost"
    oauth_redirect_port: int = 3030
    oauth_client_name: str = "Robinhood Wizard"


def load_settings(path: Path | None = None) -> Settings:
    cfg_path = path if path is not None else paths.config_path()
    if not cfg_path.exists():
        return Settings()
    data = yaml.safe_load(cfg_path.read_text()) or {}
    try:
        return Settings(**data)
    except pydantic.ValidationError as exc:
        raise ValueError(f"Invalid config at {cfg_path}: {exc}") from exc
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
uv run pytest tests/unit/test_settings.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/rh_wizard/config/settings.py tests/unit/test_settings.py
git commit -m "feat: add Settings model and YAML loader"
```

---

### Task 4: Secret-redaction log filter (`logging/redaction.py`)

**Files:**
- Create: `src/rh_wizard/logging/__init__.py`, `src/rh_wizard/logging/redaction.py`
- Test: `tests/unit/test_redaction.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `redact(text: str) -> str` — masks bearer tokens, `access_token`/`refresh_token` values, and long account-number-like digit runs.
  - `class RedactingFilter(logging.Filter)` — applies `redact()` to every record's message before emission.
  - `install_redaction(logger: logging.Logger | None = None) -> None` — attaches the filter to a logger (root if None).

- [ ] **Step 1: Write the failing test**

Write `tests/unit/test_redaction.py`:

```python
import logging

from rh_wizard.logging.redaction import RedactingFilter, install_redaction, redact


def test_redacts_bearer_token():
    out = redact("Authorization: Bearer abc123.def456.ghi789")
    assert "abc123" not in out
    assert "[REDACTED]" in out


def test_redacts_token_fields():
    out = redact('{"refresh_token": "super-secret-value-1234567890"}')
    assert "super-secret-value-1234567890" not in out
    assert "[REDACTED]" in out


def test_redacts_long_digit_runs():
    out = redact("account 1234567890123 balance")
    assert "1234567890123" not in out


def test_keeps_ordinary_text():
    assert redact("bought 3 shares of AAPL") == "bought 3 shares of AAPL"


def test_filter_scrubs_log_record(caplog):
    logger = logging.getLogger("rh_wizard.test")
    logger.addFilter(RedactingFilter())
    with caplog.at_level(logging.INFO, logger="rh_wizard.test"):
        logger.info("token Bearer abcdef12345 done")
    assert "abcdef12345" not in caplog.text


def test_install_redaction_is_idempotent():
    logger = logging.getLogger("rh_wizard.test.install")
    install_redaction(logger)
    install_redaction(logger)
    assert sum(isinstance(f, RedactingFilter) for f in logger.filters) == 1
```

- [ ] **Step 2: Run it to verify it fails**

```bash
uv run pytest tests/unit/test_redaction.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create the package marker**

Write `src/rh_wizard/logging/__init__.py`:

```python
```

(empty file)

- [ ] **Step 4: Implement `redaction.py`**

Write `src/rh_wizard/logging/redaction.py`:

```python
"""Scrub secret-shaped values from log output so logs are safe to share."""

from __future__ import annotations

import logging
import re

_MASK = "[REDACTED]"

_PATTERNS: list[re.Pattern[str]] = [
    # Bearer tokens
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.IGNORECASE),
    # JSON-ish "...token": "value"
    re.compile(
        r'("(?:access_token|refresh_token|token|client_secret)"\s*:\s*")[^"]+(")',
        re.IGNORECASE,
    ),
    # Long digit runs (account numbers, ids) — 11+ digits
    re.compile(r"\b\d{11,}\b"),
]


def redact(text: str) -> str:
    out = text
    out = _PATTERNS[0].sub(rf"\1{_MASK}", out)
    out = _PATTERNS[1].sub(rf"\1{_MASK}\2", out)
    out = _PATTERNS[2].sub(_MASK, out)
    return out


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            record.args = tuple(
                redact(a) if isinstance(a, str) else a for a in record.args
            )
        return True


def install_redaction(logger: logging.Logger | None = None) -> None:
    target = logger if logger is not None else logging.getLogger()
    if not any(isinstance(f, RedactingFilter) for f in target.filters):
        target.addFilter(RedactingFilter())
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
uv run pytest tests/unit/test_redaction.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add src/rh_wizard/logging/__init__.py src/rh_wizard/logging/redaction.py tests/unit/test_redaction.py
git commit -m "feat: add secret-redaction log filter"
```

---

### Task 5: Token persistence (`auth/token_storage.py`)

**Files:**
- Create: `src/rh_wizard/auth/__init__.py`, `src/rh_wizard/auth/token_storage.py`
- Test: `tests/unit/test_token_storage.py`

**Interfaces:**
- Consumes: `paths.tokens_path()` (Task 2).
- Produces:
  - `class TokenFile` with `__init__(self, path: pathlib.Path)`, `load(self) -> dict | None`, `save(self, data: dict) -> None` (atomic write, file mode `0600`). **This is the fully-tested persistence core.**
  - `class DiskTokenStorage` — thin adapter implementing the `mcp.client.auth.TokenStorage` protocol by delegating to `TokenFile`. (Its protocol conformance is verified live in Task 9; here we test the delegation logic via the core.)

- [ ] **Step 1: Write the failing test (persistence core)**

Write `tests/unit/test_token_storage.py`:

```python
import json
import stat

from rh_wizard.auth.token_storage import TokenFile


def test_load_missing_returns_none(tmp_path):
    assert TokenFile(tmp_path / "tokens.json").load() is None


def test_save_then_load_roundtrip(tmp_path):
    tf = TokenFile(tmp_path / "tokens.json")
    tf.save({"refresh_token": "r", "access_token": "a"})
    assert tf.load() == {"refresh_token": "r", "access_token": "a"}


def test_save_sets_mode_0600(tmp_path):
    p = tmp_path / "tokens.json"
    TokenFile(p).save({"x": 1})
    assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_save_is_atomic_no_partial_temp_left(tmp_path):
    p = tmp_path / "tokens.json"
    TokenFile(p).save({"x": 1})
    # only the final file remains; no leftover *.tmp
    leftovers = [q.name for q in tmp_path.iterdir() if q.name != "tokens.json"]
    assert leftovers == []


def test_save_overwrites(tmp_path):
    p = tmp_path / "tokens.json"
    tf = TokenFile(p)
    tf.save({"v": 1})
    tf.save({"v": 2})
    assert json.loads(p.read_text())["v"] == 2
```

- [ ] **Step 2: Run it to verify it fails**

```bash
uv run pytest tests/unit/test_token_storage.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create the package marker**

Write `src/rh_wizard/auth/__init__.py`:

```python
```

(empty file)

- [ ] **Step 4: Implement `token_storage.py` (core + adapter)**

Write `src/rh_wizard/auth/token_storage.py`:

```python
"""Persist OAuth tokens to disk with strict permissions.

``TokenFile`` is the storage core (fully unit-tested). ``DiskTokenStorage`` adapts it
to the ``mcp`` SDK's ``TokenStorage`` protocol so ``OAuthClientProvider`` can persist and
refresh tokens across headless runs. The exact protocol surface (method names, sync vs
async) is confirmed against the installed ``mcp`` version in Task 9 — keep the adapter
thin so only it changes if the protocol differs.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


class TokenFile:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> dict | None:
        if not self._path.exists():
            return None
        return json.loads(self._path.read_text())

    def save(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(data, fh)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self._path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


class DiskTokenStorage:
    """Adapter to the mcp SDK TokenStorage protocol (verified live in Task 9).

    Stores the OAuth token bundle and dynamic-client-registration info as two keys in a
    single JSON file. Serialization uses the pydantic models' ``model_dump``/
    ``model_validate`` so we never hand-roll the schemas.
    """

    def __init__(self, path: Path) -> None:
        self._file = TokenFile(path)

    def _read(self) -> dict:
        return self._file.load() or {}

    async def get_tokens(self):  # -> OAuthToken | None
        from mcp.shared.auth import OAuthToken

        blob = self._read().get("tokens")
        return OAuthToken.model_validate(blob) if blob else None

    async def set_tokens(self, tokens) -> None:
        data = self._read()
        data["tokens"] = tokens.model_dump(mode="json")
        self._file.save(data)

    async def get_client_info(self):  # -> OAuthClientInformationFull | None
        from mcp.shared.auth import OAuthClientInformationFull

        blob = self._read().get("client_info")
        return OAuthClientInformationFull.model_validate(blob) if blob else None

    async def set_client_info(self, client_info) -> None:
        data = self._read()
        data["client_info"] = client_info.model_dump(mode="json")
        self._file.save(data)
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
uv run pytest tests/unit/test_token_storage.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add src/rh_wizard/auth/__init__.py src/rh_wizard/auth/token_storage.py tests/unit/test_token_storage.py
git commit -m "feat: add disk-backed OAuth token storage"
```

---

### Task 6: OAuth localhost callback catcher (`auth/callback.py`)

**Files:**
- Create: `src/rh_wizard/auth/callback.py`
- Test: `tests/unit/test_callback.py`

**Interfaces:**
- Consumes: `oauth_redirect_host`, `oauth_redirect_port` (from `Settings`, Task 3).
- Produces:
  - `class CallbackResult(pydantic.BaseModel)` with `code: str | None`, `state: str | None`, `error: str | None`.
  - `class OAuthCallbackServer` with `__init__(self, host: str, port: int)`, `redirect_uri -> str` property (`http://{host}:{port}/callback`), `wait_for_code(self, timeout: float) -> CallbackResult` (starts a one-shot HTTP server, blocks until the browser hits `/callback?code=...`, returns the parsed result).

- [ ] **Step 1: Write the failing test**

Write `tests/unit/test_callback.py`:

```python
import threading
import urllib.request

from rh_wizard.auth.callback import OAuthCallbackServer


def test_redirect_uri_format():
    srv = OAuthCallbackServer("localhost", 3030)
    assert srv.redirect_uri == "http://localhost:3030/callback"


def test_captures_code_and_state():
    srv = OAuthCallbackServer("localhost", 0)  # port 0 -> OS-assigned
    result_box = {}

    def run():
        result_box["r"] = srv.wait_for_code(timeout=5)

    t = threading.Thread(target=run)
    t.start()
    # the server binds before wait returns; poll the resolved port
    port = srv.wait_until_listening(timeout=5)
    urllib.request.urlopen(
        f"http://localhost:{port}/callback?code=THECODE&state=xyz", timeout=5
    ).read()
    t.join(timeout=5)

    assert result_box["r"].code == "THECODE"
    assert result_box["r"].state == "xyz"


def test_captures_error():
    srv = OAuthCallbackServer("localhost", 0)
    result_box = {}

    def run():
        result_box["r"] = srv.wait_for_code(timeout=5)

    t = threading.Thread(target=run)
    t.start()
    port = srv.wait_until_listening(timeout=5)
    urllib.request.urlopen(
        f"http://localhost:{port}/callback?error=access_denied", timeout=5
    ).read()
    t.join(timeout=5)

    assert result_box["r"].error == "access_denied"
    assert result_box["r"].code is None
```

- [ ] **Step 2: Run it to verify it fails**

```bash
uv run pytest tests/unit/test_callback.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `callback.py`**

Write `src/rh_wizard/auth/callback.py`:

```python
"""A one-shot localhost HTTP server that catches the OAuth redirect.

The browser is sent to Robinhood's authorize URL with our ``redirect_uri`` pointing
here; after consent it redirects back with ``?code=...&state=...`` (or ``?error=...``),
which this server captures and hands back to the login flow.
"""

from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pydantic


class CallbackResult(pydantic.BaseModel):
    code: str | None = None
    state: str | None = None
    error: str | None = None


class OAuthCallbackServer:
    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._requested_port = port
        self._result: CallbackResult | None = None
        self._httpd: HTTPServer | None = None
        self._bound_port: int | None = None
        self._listening = threading.Event()

    @property
    def redirect_uri(self) -> str:
        port = self._bound_port or self._requested_port
        return f"http://{self._host}:{port}/callback"

    def wait_until_listening(self, timeout: float) -> int:
        if not self._listening.wait(timeout):
            raise TimeoutError("callback server did not start listening")
        assert self._bound_port is not None
        return self._bound_port

    def wait_for_code(self, timeout: float) -> CallbackResult:
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 (stdlib API name)
                qs = parse_qs(urlparse(self.path).query)
                server._result = CallbackResult(
                    code=(qs.get("code") or [None])[0],
                    state=(qs.get("state") or [None])[0],
                    error=(qs.get("error") or [None])[0],
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"Robinhood Wizard: you may close this tab.")

            def log_message(self, *args) -> None:  # silence stdlib logging
                pass

        self._httpd = HTTPServer((self._host, self._requested_port), Handler)
        self._bound_port = self._httpd.server_address[1]
        self._listening.set()

        deadline = time.monotonic() + timeout
        while self._result is None and time.monotonic() < deadline:
            self._httpd.handle_request()
        self._httpd.server_close()
        return self._result or CallbackResult(error="timeout")
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
uv run pytest tests/unit/test_callback.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/rh_wizard/auth/callback.py tests/unit/test_callback.py
git commit -m "feat: add localhost OAuth callback server"
```

---

### Task 7: OAuth provider builder (`auth/oauth.py`)

**Files:**
- Create: `src/rh_wizard/auth/oauth.py`
- Test: `tests/unit/test_oauth.py`

**Interfaces:**
- Consumes: `Settings` (Task 3), `DiskTokenStorage` (Task 5), `OAuthCallbackServer` (Task 6), the `mcp` SDK (`OAuthClientProvider`, `OAuthClientMetadata`).
- Produces:
  - `build_client_metadata(settings: Settings, redirect_uri: str) -> dict` — the OAuth client-registration metadata dict (pure; fully tested).
  - `build_oauth_provider(settings: Settings, storage, callback_server, open_browser) -> object` — assembles an `mcp.client.auth.OAuthClientProvider`. Imports the SDK lazily so the pure metadata builder stays testable without the live flow.

  > **§18 verification (resolve in Task 9, note here):** confirm whether `OAuthClientProvider`'s `server_url` should be the **base host** (`https://agent.robinhood.com`) or the **full path** (`https://agent.robinhood.com/mcp/trading`). This builder derives the base host from `settings.robinhood_mcp_url`; adjust if discovery fails.

- [ ] **Step 1: Write the failing test (pure metadata builder)**

Write `tests/unit/test_oauth.py`:

```python
from rh_wizard.auth.oauth import build_client_metadata, oauth_base_url
from rh_wizard.config.settings import Settings


def test_metadata_has_required_oauth21_fields():
    md = build_client_metadata(Settings(), "http://localhost:3030/callback")
    assert md["client_name"] == "Robinhood Wizard"
    assert md["redirect_uris"] == ["http://localhost:3030/callback"]
    assert set(md["grant_types"]) == {"authorization_code", "refresh_token"}
    assert md["response_types"] == ["code"]


def test_metadata_uses_configured_client_name():
    s = Settings(oauth_client_name="My Agent")
    md = build_client_metadata(s, "http://localhost:3030/callback")
    assert md["client_name"] == "My Agent"


def test_oauth_base_url_strips_mcp_path():
    s = Settings(robinhood_mcp_url="https://agent.robinhood.com/mcp/trading")
    assert oauth_base_url(s) == "https://agent.robinhood.com"
```

- [ ] **Step 2: Run it to verify it fails**

```bash
uv run pytest tests/unit/test_oauth.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `oauth.py`**

Write `src/rh_wizard/auth/oauth.py`:

```python
"""Assemble the mcp SDK OAuthClientProvider for the Robinhood Agentic MCP server.

The pure ``build_client_metadata`` / ``oauth_base_url`` helpers are unit-tested. The
``build_oauth_provider`` assembler imports the SDK lazily and is exercised live in
Task 9 (it needs a browser + real server).
"""

from __future__ import annotations

from typing import Callable
from urllib.parse import urlsplit, urlunsplit

from rh_wizard.config.settings import Settings


def oauth_base_url(settings: Settings) -> str:
    parts = urlsplit(settings.robinhood_mcp_url)
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def build_client_metadata(settings: Settings, redirect_uri: str) -> dict:
    return {
        "client_name": settings.oauth_client_name,
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }


def build_oauth_provider(
    settings: Settings,
    storage,
    redirect_uri: str,
    open_browser: Callable[[str], None],
    callback_handler,
):
    """Construct an OAuthClientProvider. SDK imported lazily; verify signature in Task 9."""
    from mcp.client.auth import OAuthClientProvider
    from mcp.shared.auth import OAuthClientMetadata

    return OAuthClientProvider(
        server_url=oauth_base_url(settings),
        client_metadata=OAuthClientMetadata.model_validate(
            build_client_metadata(settings, redirect_uri)
        ),
        storage=storage,
        redirect_handler=open_browser,
        callback_handler=callback_handler,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
uv run pytest tests/unit/test_oauth.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/rh_wizard/auth/oauth.py tests/unit/test_oauth.py
git commit -m "feat: add Robinhood OAuth provider builder"
```

---

### Task 8: Broker MCP client (`broker/client.py`)

**Files:**
- Create: `src/rh_wizard/broker/__init__.py`, `src/rh_wizard/broker/client.py`
- Test: `tests/unit/test_broker_client.py`

**Interfaces:**
- Consumes: `Settings` (Task 3); an OAuth provider object (Task 7); the Strands `MCPClient`.
- Produces:
  - `class BrokerClient` wrapping a Strands `MCPClient`. Constructor: `BrokerClient(mcp_client)`. Methods: `list_tool_names(self) -> list[str]`; `get_accounts(self) -> list[dict]` (calls the `get_accounts` MCP tool and returns parsed account dicts).
  - `make_broker_client(settings: Settings, oauth_provider) -> BrokerClient` — builds the authed Streamable-HTTP transport and wraps it. SDK glue verified in Task 9.

  > **§18 verification (resolve in Task 9, note here):** the `mcp` transport entrypoint has drifted. Strands docs show `from mcp.client.streamable_http import streamablehttp_client` taking `headers=`/`auth=`; `mcp>=1.28` exposes `streamable_http_client(url, *, http_client=...)`. `make_broker_client` is written for the **http_client** form (pass an `httpx.AsyncClient(auth=oauth_provider)`); if the installed version differs, switch to the `auth=` kwarg form. The unit test mocks this boundary so it is unaffected.

- [ ] **Step 1: Write the failing test (mocked MCP boundary)**

Write `tests/unit/test_broker_client.py`:

```python
from rh_wizard.broker.client import BrokerClient


class FakeTool:
    def __init__(self, name):
        self.tool_name = name


class FakeMCPClient:
    """Stand-in for strands MCPClient with the context-manager + sync call surface."""

    def __init__(self, tools, call_result):
        self._tools = tools
        self._call_result = call_result
        self.entered = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *exc):
        return False

    def list_tools_sync(self):
        return self._tools

    def call_tool_sync(self, *, name, arguments=None):
        assert self.entered, "must be used inside the client context"
        assert name == "get_accounts"
        return self._call_result


def test_list_tool_names():
    fake = FakeMCPClient([FakeTool("get_accounts"), FakeTool("get_portfolio")], None)
    with BrokerClient(fake) as broker:
        assert broker.list_tool_names() == ["get_accounts", "get_portfolio"]


def test_get_accounts_parses_results():
    payload = {"results": [{"account_number": "X1", "type": "agentic"}]}
    fake = FakeMCPClient([FakeTool("get_accounts")], {"data": payload})
    with BrokerClient(fake) as broker:
        accounts = broker.get_accounts()
    assert accounts == [{"account_number": "X1", "type": "agentic"}]
```

- [ ] **Step 2: Run it to verify it fails**

```bash
uv run pytest tests/unit/test_broker_client.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create the package marker**

Write `src/rh_wizard/broker/__init__.py`:

```python
```

(empty file)

- [ ] **Step 4: Implement `client.py`**

Write `src/rh_wizard/broker/client.py`:

```python
"""Typed wrapper over the Strands MCPClient bound to the Robinhood MCP server.

This is the single module that knows about MCP. ``BrokerClient`` adds typed helpers and
result parsing; ``make_broker_client`` builds the authenticated transport. The transport
construction is verified against the installed ``mcp`` version in Task 9 (see the §18 note
in the task header).
"""

from __future__ import annotations

import json
from typing import Any

from rh_wizard.config.settings import Settings


class BrokerClient:
    def __init__(self, mcp_client: Any) -> None:
        self._mcp = mcp_client

    def __enter__(self) -> "BrokerClient":
        self._mcp.__enter__()
        return self

    def __exit__(self, *exc) -> bool:
        return bool(self._mcp.__exit__(*exc))

    def list_tool_names(self) -> list[str]:
        return [t.tool_name for t in self._mcp.list_tools_sync()]

    def _call(self, name: str, **arguments: Any) -> dict:
        raw = self._mcp.call_tool_sync(name=name, arguments=arguments or None)
        return _coerce_payload(raw)

    def get_accounts(self) -> list[dict]:
        payload = self._call("get_accounts")
        return payload.get("data", {}).get("results", [])


def _coerce_payload(raw: Any) -> dict:
    """Normalize an MCP tool result into a dict.

    Strands may return the structured content directly, or a result object whose text
    content holds a JSON string. Handle both.
    """
    if isinstance(raw, dict):
        return raw
    text = getattr(raw, "content", None)
    if isinstance(text, str):
        return json.loads(text)
    return {}


def make_broker_client(settings: Settings, oauth_provider: Any) -> BrokerClient:
    import httpx
    from mcp.client.streamable_http import streamable_http_client
    from strands.tools.mcp import MCPClient

    def transport():
        http = httpx.AsyncClient(auth=oauth_provider, follow_redirects=True)
        return streamable_http_client(settings.robinhood_mcp_url, http_client=http)

    return BrokerClient(MCPClient(transport))
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
uv run pytest tests/unit/test_broker_client.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/rh_wizard/broker/__init__.py src/rh_wizard/broker/client.py tests/unit/test_broker_client.py
git commit -m "feat: add broker MCP client wrapper"
```

---

### Task 9: CLI `auth login` / `accounts` commands (`cli/`)

**Files:**
- Create: `src/rh_wizard/cli/__init__.py`, `src/rh_wizard/cli/app.py`, `src/rh_wizard/cli/auth.py`
- Test: `tests/unit/test_cli_auth.py`

**Interfaces:**
- Consumes: `load_settings` (Task 3), `paths.ensure_home`/`tokens_path` (Task 2), `DiskTokenStorage` (Task 5), `OAuthCallbackServer` (Task 6), `build_oauth_provider` (Task 7), `make_broker_client`/`BrokerClient` (Task 8), `install_redaction` (Task 4), the disclaimer string (Task 1).
- Produces:
  - `app: typer.Typer` — the root CLI (entry point `wizard`), prints the disclaimer banner once per run.
  - `wizard auth login` — runs the consent flow and persists tokens.
  - `wizard accounts` — connects and prints the agentic account(s), proving silent refresh.
  - Internals are injectable for testing: `auth.run_login(deps)` and `auth.run_accounts(deps)` accept a small `Deps` object so tests can substitute fakes.

- [ ] **Step 1: Write the failing test (CLI wiring with fakes)**

Write `tests/unit/test_cli_auth.py`:

```python
from typer.testing import CliRunner

from rh_wizard.cli.app import app
from rh_wizard.cli import auth

runner = CliRunner()


class FakeBroker:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_accounts(self):
        return [{"account_number": "AG-123", "type": "agentic"}]


def test_app_shows_disclaimer():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Not financial advice" in result.output


def test_accounts_command_prints_accounts(monkeypatch):
    monkeypatch.setattr(auth, "_build_broker", lambda settings: FakeBroker())
    result = runner.invoke(app, ["accounts"])
    assert result.exit_code == 0
    assert "AG-123" in result.output


def test_accounts_command_never_prints_tokens(monkeypatch):
    class LeakyBroker(FakeBroker):
        def get_accounts(self):
            return [{"account_number": "AG-123", "secret": "Bearer abcdef12345"}]

    monkeypatch.setattr(auth, "_build_broker", lambda settings: LeakyBroker())
    result = runner.invoke(app, ["accounts"])
    assert "abcdef12345" not in result.output
```

- [ ] **Step 2: Run it to verify it fails**

```bash
uv run pytest tests/unit/test_cli_auth.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create the package marker**

Write `src/rh_wizard/cli/__init__.py`:

```python
```

(empty file)

- [ ] **Step 4: Implement `cli/auth.py`**

Write `src/rh_wizard/cli/auth.py`:

```python
"""`wizard auth login` and `wizard accounts` commands."""

from __future__ import annotations

import webbrowser

import typer

from rh_wizard.auth.callback import OAuthCallbackServer
from rh_wizard.auth.oauth import build_oauth_provider
from rh_wizard.auth.token_storage import DiskTokenStorage
from rh_wizard.broker.client import make_broker_client
from rh_wizard.config import paths
from rh_wizard.config.settings import Settings, load_settings
from rh_wizard.logging.redaction import redact

auth_app = typer.Typer(help="Authenticate with the Robinhood Agentic MCP server.")


def _build_broker(settings: Settings):
    """Build an authenticated BrokerClient (real path; patched in tests)."""
    storage = DiskTokenStorage(paths.tokens_path())
    callback = OAuthCallbackServer(settings.oauth_redirect_host, settings.oauth_redirect_port)
    provider = build_oauth_provider(
        settings,
        storage,
        callback.redirect_uri,
        open_browser=lambda url: webbrowser.open(url),
        callback_handler=lambda: callback.wait_for_code(timeout=300),
    )
    return make_broker_client(settings, provider)


@auth_app.command("login")
def login() -> None:
    """Run the one-time browser consent and cache the refresh token."""
    paths.ensure_home()
    settings = load_settings()
    broker = _build_broker(settings)
    with broker:
        accounts = broker.get_accounts()
    typer.echo(f"Authenticated. Found {len(accounts)} account(s).")


def run_accounts() -> None:
    settings = load_settings()
    broker = _build_broker(settings)
    with broker:
        accounts = broker.get_accounts()
    for acct in accounts:
        typer.echo(redact(str(acct)))
```

- [ ] **Step 5: Implement `cli/app.py`**

Write `src/rh_wizard/cli/app.py`:

```python
"""Root Typer application for the `wizard` CLI."""

from __future__ import annotations

import logging

import typer

from rh_wizard.cli.auth import auth_app, run_accounts
from rh_wizard.logging.redaction import install_redaction

DISCLAIMER = (
    "DISCLAIMER: Not financial advice. No warranty. Use at your own risk. "
    "The authors are not liable for any financial loss."
)

app = typer.Typer(help=f"Robinhood Wizard.\n\n{DISCLAIMER}")
app.add_typer(auth_app, name="auth")


@app.command()
def accounts() -> None:
    """Connect to Robinhood and list your agentic account(s)."""
    run_accounts()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    install_redaction(logging.getLogger())
    app()


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run the test to verify it passes**

```bash
uv run pytest tests/unit/test_cli_auth.py -v
```

Expected: 3 passed.

- [ ] **Step 7: Run the full unit suite and lint**

```bash
uv run pytest tests/unit -v
uv run ruff check .
uv run ruff format --check .
```

Expected: all green. (Run `uv run ruff format .` first if the format check fails.)

- [ ] **Step 8: Commit**

```bash
git add src/rh_wizard/cli tests/unit/test_cli_auth.py
git commit -m "feat: add wizard auth login and accounts CLI commands"
```

---

### Task 9b: Live OAuth + MCP verification (env-gated integration)

**This task resolves the spec §18 unknowns against the real server. It is manual and not part of CI.**

**Files:**
- Create: `tests/integration/__init__.py`, `tests/integration/test_live_auth.py`

**Interfaces:**
- Consumes: the entire Phase 0 stack against the real Robinhood MCP server.
- Produces: a verified, refreshable credential at `~/.rh-wizard/tokens.json`; documented answers to the §18 unknowns.

- [ ] **Step 1: Write the env-gated live test**

Write `tests/integration/__init__.py` (empty), then `tests/integration/test_live_auth.py`:

```python
"""Live, opt-in test. Requires a real Robinhood Agentic account and a browser.

Run explicitly:
    RH_WIZARD_LIVE=1 uv run pytest tests/integration/test_live_auth.py -v -s

First run opens a browser for consent. It caches a refresh token under the configured
RH_WIZARD_HOME, after which subsequent runs must NOT open a browser (silent refresh).
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RH_WIZARD_LIVE") != "1",
    reason="set RH_WIZARD_LIVE=1 to run the live OAuth/MCP test",
)


def test_login_then_list_accounts():
    from rh_wizard.cli.auth import _build_broker
    from rh_wizard.config.settings import load_settings

    broker = _build_broker(load_settings())
    with broker:
        accounts = broker.get_accounts()
    assert isinstance(accounts, list)
    assert accounts, "expected at least one account"
```

- [ ] **Step 2: Run the live flow (first time — browser consent)**

```bash
RH_WIZARD_HOME=$(pwd)/.rh-wizard-live RH_WIZARD_LIVE=1 uv run pytest tests/integration/test_live_auth.py -v -s
```

Expected: a browser opens for Robinhood consent; after approving, the test prints/asserts at least one account. A `tokens.json` appears under `.rh-wizard-live/`.

> **If it fails, work the §18 checklist (fix in the relevant Task module, re-run):**
> 1. **Transport signature** — if `streamable_http_client(... http_client=...)` raises `TypeError`/`ImportError`, switch `broker/client.py` to `from mcp.client.streamable_http import streamablehttp_client` and `streamablehttp_client(url, auth=oauth_provider)`. Pin the working `mcp` version in `pyproject.toml`.
> 2. **TokenStorage protocol** — if `OAuthClientProvider` rejects `DiskTokenStorage` (method names / sync-vs-async mismatch), adjust the adapter in `auth/token_storage.py` to match the installed `mcp.client.auth.TokenStorage` exactly. The `TokenFile` core stays unchanged.
> 3. **Discovery `server_url`** — if discovery 404s, try passing the full `settings.robinhood_mcp_url` (path included) to `OAuthClientProvider(server_url=...)` instead of the base host in `auth/oauth.py`.
> 4. **DCR `none` auth (bug #65895)** — if dynamic client registration fails, capture the token exchange and confirm `token_endpoint_auth_method: none` + PKCE `S256` are sent; document the workaround.

- [ ] **Step 3: Run a second time (verify SILENT refresh — no browser)**

```bash
RH_WIZARD_HOME=$(pwd)/.rh-wizard-live RH_WIZARD_LIVE=1 uv run pytest tests/integration/test_live_auth.py -v -s
```

Expected: **no browser opens**; accounts are returned using the cached/refreshed token. This proves the headless-autonomy credential path.

- [ ] **Step 4: Confirm no secrets are tracked by git**

```bash
git status --porcelain
git check-ignore .rh-wizard-live/tokens.json
```

Expected: `.rh-wizard-live/` does not appear as untracked-to-be-added (it matches gitignored patterns or is outside tracked paths); `git check-ignore` prints the path (confirming it is ignored). If not ignored, add it to `.gitignore` before proceeding.

- [ ] **Step 5: Record findings in the spec**

Update `docs/superpowers/specs/2026-06-21-robinhood-wizard-design.md` §18 with the verified answers (which transport signature worked, base-vs-path `server_url`, the `TokenStorage` shape, any DCR workaround). Mark resolved items.

- [ ] **Step 6: Commit**

```bash
git add tests/integration docs/superpowers/specs/2026-06-21-robinhood-wizard-design.md
git commit -m "test: add live OAuth/MCP verification and record §18 findings"
```

---

## Phase 0 Definition of Done

- `uv run pytest tests/unit` is fully green; `uv run ruff check .` and `uv run ruff format --check .` pass; CI is green on `main`.
- MIT `LICENSE`, `README` (with disclaimer), `CONTRIBUTING.md`, `SECURITY.md`, and placeholder example config exist.
- `uv run wizard auth login` completes the OAuth consent once and caches a refresh token under `~/.rh-wizard/`.
- `uv run wizard accounts` lists the agentic account on a **second** run **without** a browser (silent refresh proven).
- No tokens, DB, or `.env` are tracked by git; logs are redacted.
- Spec §18 unknowns are resolved and recorded.

## Self-Review Notes (completed)

- **Spec coverage (Phase 0 scope):** scaffold+tooling (Task 0), MIT/OSS/disclaimer §19 (Task 1), config (Tasks 2–3), secrets-hygiene logging §19 (Task 4), auth/token persistence + OAuth + broker connection §12 (Tasks 5–8), CLI + live proof §17 Phase 0 (Tasks 9, 9b). Later phases (risk engine, data, cycle, execution, autonomy) are intentionally out of this plan per the agreed phase-by-phase approach.
- **Placeholder scan:** none — every code/test step contains complete content; the §18 "verify and adapt" steps are concrete branching instructions, not deferrals.
- **Type consistency:** `Settings` field names match across Tasks 3/7/9; `BrokerClient`/`make_broker_client`/`get_accounts`/`_build_broker` names match across Tasks 8/9/9b; `DiskTokenStorage`/`TokenFile` match across Tasks 5/9; `OAuthCallbackServer.redirect_uri`/`wait_for_code`/`wait_until_listening` match across Tasks 6/9; the `DISCLAIMER` string matches across Tasks 1/9.
