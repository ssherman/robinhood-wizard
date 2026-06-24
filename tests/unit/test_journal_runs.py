# tests/unit/test_journal_runs.py
from rh_wizard.memory.journal import SqliteJournal
from rh_wizard.models.cycle import CycleRun
from rh_wizard.models.plan import RejectedIntent, TradeIntent, VettedPlan


def _run(run_id="r1", status="completed"):
    return CycleRun(
        run_id=run_id,
        strategy_id="m",
        mode="dryrun",
        started_at="2026-06-23T00:00:00",
        finished_at="2026-06-23T00:00:01",
        status=status,
    )


def test_record_and_read_run():
    with SqliteJournal(":memory:") as j:
        j.record_run(_run())
        runs = j.recent_runs()
    assert [r.run_id for r in runs] == ["r1"]
    assert runs[0].status == "completed"


def test_record_run_upserts():
    with SqliteJournal(":memory:") as j:
        j.record_run(_run(status="completed"))
        j.record_run(_run(status="aborted"))  # same run_id
        runs = j.recent_runs()
    assert len(runs) == 1
    assert runs[0].status == "aborted"


def test_record_plan_persists_approved_and_rejected():
    vetted = VettedPlan(
        approved=[TradeIntent(side="buy", symbol="AAPL", quantity="1", limit_price="190")],
        rejected=[
            RejectedIntent(
                intent=TradeIntent(side="buy", symbol="NVDA", quantity="1", limit_price="1000"),
                reason="would exceed max position",
            )
        ],
    )
    with SqliteJournal(":memory:") as j:
        j.record_run(_run())
        j.record_plan("r1", vetted)
        rows = j.plan_intents("r1")
    buckets = {(row["symbol"], row["bucket"]): row for row in rows}
    assert ("AAPL", "approved") in buckets
    assert ("NVDA", "rejected") in buckets
    assert buckets[("NVDA", "rejected")]["reason"] == "would exceed max position"
    assert buckets[("AAPL", "approved")]["limit_price"] == "190"


def test_record_plan_replaces_prior_rows_for_run():
    with SqliteJournal(":memory:") as j:
        j.record_run(_run())
        j.record_plan(
            "r1",
            VettedPlan(
                approved=[TradeIntent(side="buy", symbol="AAPL", quantity="1", limit_price="190")]
            ),
        )
        j.record_plan(
            "r1",
            VettedPlan(
                approved=[TradeIntent(side="buy", symbol="MSFT", quantity="1", limit_price="400")]
            ),
        )
        rows = j.plan_intents("r1")
    assert [r["symbol"] for r in rows] == ["MSFT"]
