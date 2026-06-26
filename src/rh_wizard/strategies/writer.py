"""Phase 4c: write a compiled ``Strategy`` to a reviewable YAML file. The active keys are what
``StrategyRegistry.load`` parses; a leading comment header (original prose + per-ticker
rationale + web-search sources) is prepended purely for human review and is dropped by
``yaml.safe_load`` on the next load, so the file round-trips cleanly.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import yaml

from rh_wizard.models.compile import CompileResult
from rh_wizard.models.strategy import Strategy


def _num(value: Decimal):
    """Serialize a Decimal as YAML that re-loads to Decimal: int when integral, else str."""
    return int(value) if value == value.to_integral_value() else str(value)


def _bucket_to_dict(bucket) -> dict:
    return {
        "id": bucket.id,
        "name": bucket.name,
        "target_pct": _num(bucket.target_pct),
        "intent": bucket.intent,
        "universe": list(bucket.universe),
        "discover": bucket.discover,
        "max_candidates": bucket.max_candidates,
    }


def _strategy_to_dict(strategy: Strategy) -> dict:
    if strategy.buckets:
        return {
            "id": strategy.id,
            "name": strategy.name,
            "intent": strategy.intent,
            "signals_needed": sorted(s.value for s in strategy.signals_needed),
            "cadence": strategy.cadence,
            "allow_fractional": strategy.allow_fractional,
            "rebalance_mode": strategy.rebalance_mode,
            "rebalance_band_pct": _num(strategy.rebalance_band_pct),
            "risk_overrides": dict(strategy.risk_overrides),
            "buckets": [_bucket_to_dict(b) for b in strategy.buckets],
        }
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
    if result.buckets:
        for b in result.buckets:
            lines += ["#", f"# Bucket: {b.name} ({b.target_pct}% of investable)"]
            for t in b.tickers:
                ticker_line = (
                    f"#   {t.symbol} - {t.rationale}" if t.rationale else f"#   {t.symbol}"
                )
                lines.append(ticker_line)
    elif result.tickers:
        lines += ["#", "# Suggested tickers:"]
        for t in result.tickers:
            ticker_line = f"#   {t.symbol} - {t.rationale}" if t.rationale else f"#   {t.symbol}"
            lines.append(ticker_line)
    if result.sources:
        lines += ["#", "# Sources:"]
        for s in result.sources:
            lines.append(f"#   - {s.title}  {s.url}" if s.title else f"#   - {s.url}")
    lines.append("")
    return "\n".join(lines)


def write_strategy_yaml(path: Path, result: CompileResult, prose: str) -> None:
    body = yaml.safe_dump(
        _strategy_to_dict(result.strategy), sort_keys=False, default_flow_style=False
    )
    path.write_text(_comment_header(result, prose) + body, encoding="utf-8")
