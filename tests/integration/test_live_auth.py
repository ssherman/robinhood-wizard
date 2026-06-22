"""Live, opt-in test. Requires a real Robinhood Agentic account and a browser.

Run explicitly:
    RH_WIZARD_LIVE=1 uv run pytest tests/integration/test_live_auth.py -v -s

First run opens a browser for consent. It caches a refresh token under the configured
RH_WIZARD_HOME, after which subsequent runs must NOT open a browser (silent refresh).
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RH_WIZARD_LIVE") != "1",
    reason="set RH_WIZARD_LIVE=1 to run the live OAuth/MCP test",
)


def test_login_then_list_accounts():
    from rh_wizard.cli.auth import _build_broker
    from rh_wizard.config.settings import load_settings

    broker = _build_broker(load_settings())
    with broker:
        accounts = broker.get_accounts()
    assert isinstance(accounts, list)
    assert accounts, "expected at least one account"
