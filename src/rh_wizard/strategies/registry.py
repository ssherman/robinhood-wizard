"""Load strategies from YAML files in a directory (spec §5).

Each ``<id>.yaml`` holds one ``Strategy``. ``list()`` returns the available ids; ``load(id)``
parses ``<id>.yaml``. Code-module strategies are a later extension point.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from rh_wizard.models.strategy import Strategy


class StrategyNotFoundError(Exception):
    pass


class StrategyRegistry:
    def __init__(self, directory: Path) -> None:
        self._dir = Path(directory)

    def list(self) -> list[str]:
        if not self._dir.is_dir():
            return []
        return sorted(p.stem for p in self._dir.glob("*.yaml"))

    def load(self, strategy_id: str) -> Strategy:
        path = self._dir / f"{strategy_id}.yaml"
        if not path.is_file():
            raise StrategyNotFoundError(f"Strategy '{strategy_id}' not found in {self._dir}")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return Strategy(**data)
