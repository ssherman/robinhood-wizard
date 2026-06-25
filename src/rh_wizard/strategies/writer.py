"""Phase 4c: write a compiled ``Strategy`` to a reviewable YAML file. The active keys are what
``StrategyRegistry.load`` parses; a leading comment header (original prose + per-ticker
rationale + web-search sources) is prepended purely for human review and is dropped by
``yaml.safe_load`` on the next load, so the file round-trips cleanly.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from rh_wizard.models.compile import CompileResult
from rh_wizard.models.strategy import Strategy


def _strategy_to_dict(strategy: Strategy) -> dict:
    return {
        "id": strategy.id,
        "name": strategy.name,
        "intent": strategy.intent,
        "universe": list(strategy.universe),
        "signals_needed": sorted(s.value for s in strategy.signals_needed),
        "cadence": strategy.cadence,
        "risk_overrides": dict(strategy.risk_overrides),
        "web_research": strategy.web_research,
    }


def _comment_header(result: CompileResult, prose: str) -> str:
    lines = [
        "# Compiled by `wizard compile`. Review the suggested universe before running —",
        "# these are LLM web-search suggestions, not vetted picks.",
        "#",
        "# Original thesis:",
    ]
    lines += [f"#   {ln}" for ln in (prose.strip().splitlines() or [""])]
    if result.tickers:
        lines += ["#", "# Suggested tickers:"]
        for t in result.tickers:
            lines.append(f"#   {t.symbol} - {t.rationale}" if t.rationale else f"#   {t.symbol}")
    if result.sources:
        lines += ["#", "# Sources:"]
        for s in result.sources:
            lines.append(f"#   - {(s.title or s.url)}  {s.url}")
    lines.append("")  # trailing newline before the YAML body
    return "\n".join(lines)


def write_strategy_yaml(path: Path, result: CompileResult, prose: str) -> None:
    body = yaml.safe_dump(
        _strategy_to_dict(result.strategy), sort_keys=False, default_flow_style=False
    )
    path.write_text(_comment_header(result, prose) + body, encoding="utf-8")
