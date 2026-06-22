import pytest

from rh_wizard.config.settings import Settings
from rh_wizard.memory.portfolio import (
    AccountSelectionError,
    resolve_account_number,
    select_account,
)


def test_single_account_is_selected():
    accounts = [{"account_number": "ACC1", "type": "agentic"}]
    assert select_account(accounts)["account_number"] == "ACC1"


def test_pinned_account_is_selected():
    accounts = [{"account_number": "ACC1"}, {"account_number": "ACC2"}]
    assert select_account(accounts, pinned="ACC2")["account_number"] == "ACC2"


def test_agentic_account_chosen_when_multiple():
    # Real Phase 0 shape: agentic account is flagged agentic_allowed=true, not by type.
    accounts = [
        {"account_number": "5PY29149", "type": "margin", "agentic_allowed": False},
        {"account_number": "766943641", "type": "cash", "agentic_allowed": True},
    ]
    assert select_account(accounts)["account_number"] == "766943641"


def test_agentic_account_chosen_by_nickname_fallback():
    accounts = [
        {"account_number": "ACC1", "type": "margin"},
        {"account_number": "ACC2", "type": "cash", "nickname": "Agentic"},
    ]
    assert select_account(accounts)["account_number"] == "ACC2"


def test_ambiguous_multiple_raises():
    accounts = [{"account_number": "ACC1"}, {"account_number": "ACC2"}]
    with pytest.raises(AccountSelectionError):
        select_account(accounts)


def test_empty_raises():
    with pytest.raises(AccountSelectionError):
        select_account([])


def test_pinned_not_found_raises():
    with pytest.raises(AccountSelectionError):
        select_account([{"account_number": "ACC1"}], pinned="NOPE")


def test_resolve_uses_broker_and_settings():
    class FakeBroker:
        def get_accounts(self):
            return [{"account_number": "ACC1", "type": "agentic"}]

    assert resolve_account_number(FakeBroker(), Settings()) == "ACC1"
