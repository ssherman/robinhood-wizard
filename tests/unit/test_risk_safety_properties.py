# tests/unit/test_risk_safety_properties.py
from decimal import Decimal

from rh_wizard.models.market import SymbolRisk
from rh_wizard.models.plan import TradeIntent, TradePlan
from rh_wizard.models.portfolio import PortfolioState
from rh_wizard.models.risk import RiskCeiling, RiskPolicy
from rh_wizard.risk.engine import _order_value, vet
from rh_wizard.risk.policy import build_effective_policy


def _portfolio(cash="10000"):
    return PortfolioState(
        account_number="ACC1",
        positions=[],
        cash=Decimal(cash),
        buying_power=Decimal(cash),
        total_value=Decimal(cash),
    )


def _market(*symbols):
    return {
        s: SymbolRisk(
            symbol=s,
            price=Decimal("100"),
            average_volume=Decimal("50000000"),
            market_cap=Decimal("3000000000000"),
        )
        for s in symbols
    }


def test_no_approved_buy_exceeds_position_or_deploy_or_reserve():
    # Throw many oversized/again-and-again buys at the engine; every APPROVED buy must
    # individually respect position cap, and the set must respect cash reserve + deploy cap.
    policy = RiskPolicy()  # 20% position, 10% reserve, 30% deploy, 5 trades
    pv = Decimal("10000")
    syms = [f"S{i}" for i in range(10)]
    intents = [
        TradeIntent(side="buy", symbol=s, quantity="10", limit_price="100")  # $1000 each (10%)
        for s in syms
    ]
    result = vet(TradePlan(intents=intents), policy, _portfolio(), _market(*syms))
    assert result.approved  # some buys fit (deploy cap binds at 30% = three $1000 buys)

    # Every approved buy is within the per-position cap.
    for i in result.approved:
        assert _order_value(i) / pv * 100 <= policy.max_position_pct
    # Cumulative deploy within the cap.
    total = sum(_order_value(i) for i in result.approved)
    assert total / pv * 100 <= policy.max_deploy_pct_per_cycle
    # Cash reserve preserved.
    assert _portfolio().cash - total >= pv * policy.cash_reserve_pct / 100
    # Trade-count cap.
    assert len(result.approved) <= policy.max_trades_per_cycle


def test_ceiling_makes_reckless_override_safe():
    # A strategy tries max_position 100% and 50 trades; the ceiling forces it back.
    defaults = RiskPolicy()
    ceiling = RiskCeiling(max_position_pct="20", max_trades_per_cycle="5")
    policy = build_effective_policy(
        defaults, ceiling, {"max_position_pct": "100", "max_trades_per_cycle": 50}
    )
    assert policy.max_position_pct == Decimal("20")  # clamped down from 100
    assert policy.max_trades_per_cycle == 5  # clamped down from 50
    # A $5000 buy (50% of a $10k portfolio) would pass under the reckless 100% override,
    # but the clamped 20% policy rejects it — proving the ceiling protected us.
    plan = TradePlan(
        intents=[TradeIntent(side="buy", symbol="S0", quantity="50", limit_price="100")]
    )
    result = vet(plan, policy, _portfolio(), _market("S0"))
    assert result.approved == []
    assert "position" in result.rejected[0].reason.lower()


def test_empty_plan_yields_empty_vetted_plan():
    result = vet(TradePlan(intents=[]), RiskPolicy(), _portfolio(), {})
    assert result.approved == [] and result.rejected == [] and result.adjusted == []
