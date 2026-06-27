"""Interactive whole-plan approval gate (Phase 5). The ONLY interactive surface in the
execution path: it renders a pre-flight summary of the vetted plan (orders, total estimated
deploy, masked agentic account) and requires the operator to type exactly ``yes`` before any
real order is placed. It never places orders itself.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from typing import TextIO

from rh_wizard.cli.render import _intent_amount, fmt_money, fmt_num
from rh_wizard.masking import mask_account
from rh_wizard.models.plan import VettedPlan
from rh_wizard.models.portfolio import PortfolioState


class CliApprovalGate:
    def __init__(self, stdin: TextIO | None = None) -> None:
        self._stdin = stdin if stdin is not None else sys.stdin

    def confirm(self, vetted: VettedPlan, portfolio: PortfolioState, account: str) -> bool:
        total = sum((_intent_amount(i) or Decimal("0")) for i in vetted.approved)
        print(
            f"\nAbout to place {len(vetted.approved)} REAL order(s) "
            f"(~{fmt_money(total)}) in account {mask_account(account)}:"
        )
        for i in vetted.approved:
            qty = fmt_num(i.quantity) if i.quantity is not None else "-"
            kind = "limit" if i.limit_price is not None and i.amount is None else "market"
            print(
                f"  {i.side} {i.symbol}  qty={qty}  {kind} {fmt_money(i.limit_price)}  "
                f"amount={fmt_money(_intent_amount(i))}"
            )
        print("Type 'yes' to place these orders (anything else cancels): ", end="")
        answer = self._stdin.readline().strip()
        return answer == "yes"
