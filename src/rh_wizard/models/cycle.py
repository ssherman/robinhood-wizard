"""Cycle audit models (spec §7/§8).

``CycleMode`` is the execution-mode seam (only ``DRY_RUN`` is implemented in Phase 4a;
``HUMAN_APPROVAL``/``AUTONOMOUS`` are declared seams for Phases 5/6). ``CycleRun`` is the
per-run audit record persisted by the journal.
"""

from __future__ import annotations

from enum import StrEnum

import pydantic


class CycleMode(StrEnum):
    DRY_RUN = "dryrun"
    HUMAN_APPROVAL = "human_approval"  # Phase 5 seam
    AUTONOMOUS = "autonomous"  # Phase 6 seam


class CycleRun(pydantic.BaseModel):
    run_id: str
    strategy_id: str
    mode: str
    started_at: str  # ISO timestamp
    finished_at: str | None = None
    status: str = "completed"  # completed | aborted
    note: str = ""  # abort reason / notes
