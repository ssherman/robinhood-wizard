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
            update={
                "status": "aborted",
                "finished_at": _now(),
                "note": f"research/plan failed: {exc}",
            }
        )
        deps.journal.record_run(run)
        return CycleResult(run=run, portfolio=portfolio, market=market)

    # Stage 9: DryRun — no execution (Phase 5 adds the executor). Stage 11: JOURNAL.
    run = run.model_copy(update={"status": "completed", "finished_at": _now()})
    deps.journal.record_run(run)
    deps.journal.record_plan(run.run_id, vetted)

    return CycleResult(
        run=run, portfolio=portfolio, market=market, report=report, plan=plan, vetted=vetted
    )
