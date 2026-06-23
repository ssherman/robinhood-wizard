"""Live, opt-in shape verification against the real Robinhood MCP (read-only).

Run explicitly (needs a cached token from `wizard auth login`):
    RH_WIZARD_LIVE=1 uv run pytest tests/integration/test_live_portfolio.py -v -s

Prints a summary of the reconciled portfolio and synced history so the parsers can be
sanity-checked (see spec §18). The account number is masked in output per §19 hygiene.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RH_WIZARD_LIVE") != "1",
    reason="set RH_WIZARD_LIVE=1 to run the live portfolio test",
)


def test_reconcile_and_history_live(tmp_path):
    from rh_wizard.cli import auth
    from rh_wizard.config.settings import load_settings
    from rh_wizard.masking import mask_account
    from rh_wizard.memory.journal import SqliteJournal
    from rh_wizard.memory.portfolio import (
        enrich_with_quotes,
        reconcile,
        resolve_account_number,
    )
    from rh_wizard.memory.sync import sync_equity_orders

    settings = load_settings()
    broker = auth._build_broker(settings)
    with broker:
        state = enrich_with_quotes(reconcile(broker, settings), broker)
        account_number = resolve_account_number(broker, settings)
        with SqliteJournal(tmp_path / "wizard.db") as journal:
            synced = sync_equity_orders(broker, account_number, journal)
            trades = journal.recent_trades()

    print(f"\nAccount: {mask_account(state.account_number)}")
    print(f"Cash: {state.cash}   Buying power: {state.buying_power}")
    print(f"Positions: {len(state.positions)}   Synced orders: {synced}   Trades: {len(trades)}")
    for p in state.positions:
        print(f"  {p.symbol}: qty={p.quantity} avg={p.average_cost} mkt={p.market_value}")

    assert state.account_number
    assert isinstance(state.positions, list)
    assert isinstance(trades, list)
