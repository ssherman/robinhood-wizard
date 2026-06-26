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

from rh_wizard.allocation.base import BucketRecommender
from rh_wizard.allocation.engine import allocate
from rh_wizard.config.settings import Settings
from rh_wizard.data.resolver import SignalResolver
from rh_wizard.discovery.base import UniverseDiscoverer
from rh_wizard.memory.journal import SqliteJournal
from rh_wizard.memory.portfolio import enrich_with_quotes, reconcile
from rh_wizard.models.allocation import AllocationRecommendation, AllocationReport
from rh_wizard.models.bucket import Bucket
from rh_wizard.models.cycle import CycleMode, CycleRun
from rh_wizard.models.discovery import DiscoveryResult
from rh_wizard.models.market import MarketContext
from rh_wizard.models.plan import TradePlan, VettedPlan
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.research import ResearchReport
from rh_wizard.models.signals import RISK_SIGNALS, Signal
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
    discoverer: UniverseDiscoverer | None = None
    recommender: BucketRecommender | None = None


@dataclass
class CycleResult:
    run: CycleRun
    portfolio: PortfolioState | None = None
    market: MarketContext | None = None
    report: ResearchReport | None = None
    plan: TradePlan | None = None
    vetted: VettedPlan | None = None
    discovery: DiscoveryResult | None = None
    recommendation: AllocationRecommendation | None = None
    allocation: AllocationReport | None = None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _norm(symbol: str) -> str:
    return symbol.strip().upper()


def _bucket_discovery_view(strategy: Strategy, bucket: Bucket) -> Strategy:
    """A minimal flat Strategy so the existing discoverer can run for one bucket's theme."""
    return Strategy(
        id=f"{strategy.id}:{bucket.id}",
        name=f"{strategy.name}: {bucket.name or bucket.id}",
        intent=bucket.intent,
        max_candidates=bucket.max_candidates,
    )


def _bucket_candidates(
    strategy: Strategy, deps: CycleDeps
) -> tuple[dict[str, list[str]], list[str]]:
    """Per-bucket candidate symbols (explicit ∪ discovered) and any degrade notes."""
    candidates: dict[str, list[str]] = {}
    notes: list[str] = []
    for bucket in strategy.buckets:
        syms = {_norm(s) for s in bucket.universe}
        if bucket.discover and deps.discoverer is not None:
            try:
                discovered = deps.discoverer.discover(_bucket_discovery_view(strategy, bucket))
                syms |= {_norm(t.symbol) for t in discovered.tickers}
            except Exception as exc:  # discovery is best-effort; bucket keeps its explicit universe
                notes.append(f"discovery failed for bucket {bucket.id}: {exc}")
        candidates[bucket.id] = sorted(syms)
    return candidates, notes


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

    if strategy.buckets:
        return _run_bucketed(strategy, deps, run, portfolio)

    # Stage 4.5 (DISCOVER) — opt-in; degrade-and-report on failure (never abort).
    discovery: DiscoveryResult | None = None
    discovery_note = ""
    if strategy.discover and deps.discoverer is not None:
        try:
            discovery = deps.discoverer.discover(strategy)
        except Exception as exc:  # discovery is best-effort; the cycle still runs
            discovery_note = f"discovery failed: {exc}"

    discovered = {_norm(t.symbol) for t in discovery.tickers} if discovery else set()

    # Stage 5 (RESOLVE SIGNALS) over explicit universe ∪ discovered ∪ current holdings.
    universe = sorted(
        {_norm(s) for s in strategy.universe}
        | {_norm(p.symbol) for p in portfolio.positions}
        | discovered
    )
    needed = set(strategy.signals_needed) | set(RISK_SIGNALS)
    market = deps.resolver.resolve(universe, needed)
    if discovery_note:
        market = market.model_copy(update={"notes": [*market.notes, discovery_note]})

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
        return CycleResult(run=run, portfolio=portfolio, market=market, discovery=discovery)

    # Stage 9: DryRun — no execution (Phase 5 adds the executor). Stage 11: JOURNAL.
    run = run.model_copy(update={"status": "completed", "finished_at": _now()})
    deps.journal.record_run(run)
    deps.journal.record_plan(run.run_id, vetted)
    deps.journal.record_research(run.run_id, report)
    if discovery is not None:
        deps.journal.record_discovery(run.run_id, discovery)

    return CycleResult(
        run=run,
        portfolio=portfolio,
        market=market,
        report=report,
        plan=plan,
        vetted=vetted,
        discovery=discovery,
    )


def _run_bucketed(
    strategy: Strategy, deps: CycleDeps, run: CycleRun, portfolio: PortfolioState
) -> CycleResult:
    candidates, notes = _bucket_candidates(strategy, deps)
    candidate_syms = {s for syms in candidates.values() for s in syms}
    held_syms = {_norm(p.symbol) for p in portfolio.positions}
    universe = sorted(candidate_syms | held_syms)
    needed = set(strategy.signals_needed) | set(RISK_SIGNALS) | {Signal.FRACTIONABLE}
    market = deps.resolver.resolve(universe, needed)
    if notes:
        market = market.model_copy(update={"notes": [*market.notes, *notes]})

    if deps.recommender is None:
        run = run.model_copy(
            update={
                "status": "aborted",
                "finished_at": _now(),
                "note": "bucketed strategy requires a recommender",
            }
        )
        deps.journal.record_run(run)
        return CycleResult(run=run, portfolio=portfolio, market=market)

    try:
        recommendation = deps.recommender.recommend(strategy, candidates, market, portfolio)
        policy = build_effective_policy(
            deps.settings.risk, deps.settings.risk_ceiling, strategy.risk_overrides
        )
        plan, allocation = allocate(strategy, recommendation, policy, portfolio, market.symbols)
        vetted = vet(plan, policy, portfolio, market.to_symbol_risk())
    except Exception as exc:
        run = run.model_copy(
            update={
                "status": "aborted",
                "finished_at": _now(),
                "note": f"recommend/allocate/vet failed: {exc}",
            }
        )
        deps.journal.record_run(run)
        return CycleResult(run=run, portfolio=portfolio, market=market)

    run = run.model_copy(update={"status": "completed", "finished_at": _now()})
    deps.journal.record_run(run)
    deps.journal.record_plan(run.run_id, vetted)
    deps.journal.record_allocation(run.run_id, allocation, recommendation)
    return CycleResult(
        run=run,
        portfolio=portfolio,
        market=market,
        plan=plan,
        vetted=vetted,
        recommendation=recommendation,
        allocation=allocation,
    )
