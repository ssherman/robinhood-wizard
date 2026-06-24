from decimal import Decimal

from rh_wizard.models.cycle import CycleMode, CycleRun
from rh_wizard.models.research import Candidate, ResearchReport


def test_candidate_and_report_defaults():
    r = ResearchReport()
    assert r.candidates == []
    assert r.summary == ""
    c = Candidate(symbol="AAPL", thesis="cheap", conviction="0.7")
    assert c.conviction == Decimal("0.7")


def test_cycle_mode_values():
    assert CycleMode.DRY_RUN == "dryrun"
    assert CycleMode.HUMAN_APPROVAL.value == "human_approval"
    assert CycleMode.AUTONOMOUS.value == "autonomous"


def test_cycle_run_defaults_completed():
    run = CycleRun(run_id="r1", strategy_id="m", mode="dryrun", started_at="2026-06-23T00:00:00")
    assert run.status == "completed"
    assert run.finished_at is None
    assert run.note == ""
