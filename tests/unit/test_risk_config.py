from decimal import Decimal

from rh_wizard.config.settings import Settings, load_settings
from rh_wizard.risk.policy import build_effective_policy


def test_settings_has_default_risk_policy():
    s = Settings()
    assert s.risk.max_position_pct == Decimal("20")
    assert s.risk_ceiling is None


def test_settings_loads_risk_block(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "risk:\n"
        "  max_position_pct: 15\n"
        "  max_trades_per_cycle: 3\n"
        "risk_ceiling:\n"
        "  max_position_pct: 25\n"
    )
    s = load_settings(cfg)
    assert s.risk.max_position_pct == Decimal("15")
    assert s.risk.max_trades_per_cycle == 3
    assert s.risk_ceiling.max_position_pct == Decimal("25")


def test_config_drives_effective_policy(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("risk_ceiling:\n  max_position_pct: 25\n")
    s = load_settings(cfg)
    # a reckless strategy override is clamped by the configured ceiling
    eff = build_effective_policy(s.risk, s.risk_ceiling, {"max_position_pct": "90"})
    assert eff.max_position_pct == Decimal("25")
