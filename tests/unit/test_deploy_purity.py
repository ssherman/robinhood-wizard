"""core/deploy.py must stay pure + brain-agnostic: no I/O layers (broker, auth, memory, cli, llm)."""  # noqa: E501

import ast
from pathlib import Path

FORBIDDEN = ("broker", "auth", "memory", "cli", "llm")
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


def test_deploy_module_does_not_import_io_layers():
    mods = _imported_modules(ROOT / "src/rh_wizard/core/deploy.py")
    for m in mods:
        for layer in FORBIDDEN:
            assert f"rh_wizard.{layer}" not in m, f"deploy.py imports forbidden layer: {m}"
