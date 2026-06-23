# tests/unit/test_risk_engine_purity.py
"""The risk engine must be pure: it may not import I/O layers (broker, auth, memory, cli,
llm). It depends only on models and the stdlib."""

import ast
from pathlib import Path

FORBIDDEN = ("broker", "auth", "memory", "cli", "llm")
ENGINE_FILES = ["src/rh_wizard/risk/engine.py", "src/rh_wizard/risk/policy.py"]
ROOT = Path(__file__).resolve().parents[2]


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def test_risk_modules_do_not_import_io_layers():
    for rel in ENGINE_FILES:
        mods = _imported_modules(ROOT / rel)
        for m in mods:
            for layer in FORBIDDEN:
                assert f"rh_wizard.{layer}" not in m, f"{rel} imports forbidden layer: {m}"
