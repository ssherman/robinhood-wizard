"""The universe-discovery seam (Phase 4d). A discoverer turns a strategy's free-text thesis
into a candidate ticker list. ``WebUniverseDiscoverer`` (separate module) is the v1
implementation; the cycle depends on this Protocol so it stays brain-agnostic and testable
without an LLM. A future Robinhood-scan discoverer implements the same Protocol.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rh_wizard.models.discovery import DiscoveryResult
from rh_wizard.models.strategy import Strategy


@runtime_checkable
class UniverseDiscoverer(Protocol):
    def discover(self, strategy: Strategy) -> DiscoveryResult: ...
