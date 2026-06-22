"""Account selection and live reconciliation (spec §8 step 3).

The broker is ground truth: every call here reads live state. Nothing trusts local
storage for holdings.
"""

from __future__ import annotations

from decimal import Decimal

from rh_wizard.cli.render import mask_account
from rh_wizard.models.portfolio import PortfolioState, Position


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
    if pinned is not None:
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
        unrealized_pl_pct = unrealized_pl / p.cost_basis * 100 if p.cost_basis else None
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
