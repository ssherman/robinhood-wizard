"""`wizard compile <id>` — compile a plain-language strategy description into a reviewable
``Strategy`` YAML in ~/.rh-wizard/strategies/. Talks only to the LLM (web search): no broker,
no auth, no orders. Review the written file, then run `wizard run <id>`.
"""

from __future__ import annotations

from pathlib import Path

import typer

from rh_wizard.config import paths
from rh_wizard.config.settings import load_settings
from rh_wizard.llm.base import LlmError
from rh_wizard.models.compile import CompileResult
from rh_wizard.strategies.writer import write_strategy_yaml

_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")


def _build_compiler(settings):
    """Build the web-search-backed compiler (real path; patched in tests)."""
    from rh_wizard.llm.openai_web import OpenAiWebSearchLlm
    from rh_wizard.llm.web_search import RetryingWebSearchLlm
    from rh_wizard.strategies.compiler import LlmStrategyCompiler

    return LlmStrategyCompiler(RetryingWebSearchLlm(OpenAiWebSearchLlm(settings)))


def _read_prose(file: Path | None, text: str | None) -> str:
    if (file is None) == (text is None):
        raise typer.BadParameter("Provide exactly one of --file or --text.")
    if text is not None:
        prose = text
    else:
        if not file.is_file():
            raise typer.BadParameter(f"File not found: {file}")
        prose = file.read_text(encoding="utf-8")
    if not prose.strip():
        raise typer.BadParameter("Strategy description is empty.")
    return prose


def _render_summary(result: CompileResult, path: Path, strategy_id: str) -> str:
    lines = [
        f"Compiled '{strategy_id}' -> {path}",
        f"Name: {result.strategy.name}",
        "Suggested universe:",
    ]
    for t in result.tickers:
        lines.append(f"  {t.symbol} - {t.rationale}" if t.rationale else f"  {t.symbol}")
    if result.sources:
        lines.append("Sources:")
        for s in result.sources:
            lines.append(f"  - {s.title}  {s.url}" if s.title else f"  - {s.url}")
    lines.append(f"Review the file, then: wizard run {strategy_id}")
    return "\n".join(lines)


def compile_strategy(strategy_id: str, file: Path | None, text: str | None, force: bool) -> None:
    if not strategy_id or any(ch not in _ID_CHARS for ch in strategy_id):
        raise typer.BadParameter(
            "Strategy id must be a simple filename stem (letters, digits, '-', '_')."
        )
    prose = _read_prose(file, text)

    paths.ensure_home()
    strategies_dir = paths.strategies_dir()
    strategies_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    out_path = strategies_dir / f"{strategy_id}.yaml"
    if out_path.exists() and not force:
        raise typer.BadParameter(f"{out_path} exists; pass --force to overwrite.")

    settings = load_settings()
    compiler = _build_compiler(settings)
    try:
        result = compiler.compile(strategy_id, prose)
    except LlmError as exc:
        typer.echo(f"Compile failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    write_strategy_yaml(out_path, result, prose)
    typer.echo(_render_summary(result, out_path, strategy_id))
