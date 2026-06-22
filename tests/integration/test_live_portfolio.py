"""Live, opt-in shape verification against the real Robinhood MCP (read-only).

Run explicitly (needs a cached token from `wizard auth login`):
    RH_WIZARD_LIVE=1 uv run pytest tests/integration/test_live_portfolio.py -v -s

Prints the reconciled portfolio and synced history so the assumed payload field names in
the broker/reconcile/sync parsers can be confirmed (see spec §18).
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

    print("\nPortfolioState:", state.model_dump())
    print("Synced orders:", synced)
    print("Recent trades:", [t.model_dump() for t in trades])

    assert state.account_number
    assert isinstance(state.positions, list)
    assert isinstance(trades, list)
