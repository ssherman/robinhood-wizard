"""Account selection and live reconciliation (spec §8 step 3).

The broker is ground truth: every call here reads live state. Nothing trusts local
storage for holdings.
"""

from __future__ import annotations

from rh_wizard.cli.render import mask_account


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
