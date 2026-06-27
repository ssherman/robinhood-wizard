"""The order-execution seams (Phase 5). ``OrderExecutor`` reviews then places a single
``TradeIntent`` (the broker boundary). ``ApprovalGate`` asks the human whether to place the
whole vetted plan. The cycle depends on these Protocols so it stays non-interactive and
testable without a broker or a terminal.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rh_wizard.models.order import OrderResult, ReviewResult
from rh_wizard.models.plan import TradeIntent, VettedPlan
from rh_wizard.models.portfolio import PortfolioState


@runtime_checkable
class OrderExecutor(Protocol):
    def review(self, intent: TradeIntent, account: str) -> ReviewResult: ...
    def place(self, intent: TradeIntent, account: str, ref_id: str) -> OrderResult: ...


@runtime_checkable
class ApprovalGate(Protocol):
    def confirm(self, vetted: VettedPlan, portfolio: PortfolioState, account: str) -> bool: ...
