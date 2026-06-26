import os

import pytest
from typer.testing import CliRunner

from rh_wizard.cli import compile as compile_module
from rh_wizard.cli.app import app
from rh_wizard.models.compile import CompileResult, SuggestedTicker
from rh_wizard.models.research import Source
from rh_wizard.models.strategy import Strategy

runner = CliRunner()


class FakeCompiler:
    def compile(self, strategy_id, prose):
        strategy = Strategy(
            id=strategy_id,
            name="Large-Cap AI",
            intent=prose,
            universe=["MSFT", "META"],
            web_research=True,
        )
        return CompileResult(
            strategy=strategy,
            tickers=[SuggestedTicker(symbol="MSFT", rationale="azure")],
            sources=[Source(title="src", url="https://e/ai")],
        )


def _patch(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))
    monkeypatch.setattr(compile_module, "_build_compiler", lambda settings: FakeCompiler())


def test_compile_text_writes_file_and_renders(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    result = runner.invoke(app, ["compile", "ai", "--text", "large-cap ai"])
    assert result.exit_code == 0, result.output
    out = tmp_path / "strategies" / "ai.yaml"
    assert out.is_file()
    assert "MSFT" in out.read_text(encoding="utf-8")
    assert "wizard run ai" in result.output


def test_compile_file_reads_prose(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    thesis = tmp_path / "thesis.txt"
    thesis.write_text("large-cap ai with reasonable valuations", encoding="utf-8")
    result = runner.invoke(app, ["compile", "ai", "--file", str(thesis)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "strategies" / "ai.yaml").is_file()


def test_compile_refuses_existing_without_force(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    d = tmp_path / "strategies"
    d.mkdir(parents=True)
    (d / "ai.yaml").write_text("id: ai\nname: old\n", encoding="utf-8")
    result = runner.invoke(app, ["compile", "ai", "--text", "x"])
    assert result.exit_code != 0
    assert "force" in result.output.lower()
    assert "old" in (d / "ai.yaml").read_text(encoding="utf-8")  # untouched


def test_compile_force_overwrites(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    d = tmp_path / "strategies"
    d.mkdir(parents=True)
    (d / "ai.yaml").write_text("id: ai\nname: old\n", encoding="utf-8")
    result = runner.invoke(app, ["compile", "ai", "--text", "x", "--force"])
    assert result.exit_code == 0, result.output
    assert "Large-Cap AI" in (d / "ai.yaml").read_text(encoding="utf-8")


def test_compile_requires_exactly_one_input(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    assert runner.invoke(app, ["compile", "ai"]).exit_code != 0
    both = runner.invoke(app, ["compile", "ai", "--text", "x", "--file", "y.txt"])
    assert both.exit_code != 0


def test_compile_rejects_unsafe_id(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    assert runner.invoke(app, ["compile", "../evil", "--text", "x"]).exit_code != 0


def test_compile_llm_error_exits_nonzero_and_writes_nothing(monkeypatch, tmp_path):
    from rh_wizard.llm.base import LlmError

    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))

    class ErrorCompiler:
        def compile(self, strategy_id, prose):
            raise LlmError("API failure")

    monkeypatch.setattr(compile_module, "_build_compiler", lambda settings: ErrorCompiler())
    result = runner.invoke(app, ["compile", "ai", "--text", "x"])
    assert result.exit_code != 0
    assert not (tmp_path / "strategies" / "ai.yaml").exists()


class FakeBucketedCompiler:
    def compile(self, strategy_id, prose):
        from decimal import Decimal

        from rh_wizard.models.bucket import Bucket
        from rh_wizard.models.compile import CompiledBucket

        strategy = Strategy(
            id=strategy_id,
            name="Thematic",
            intent=prose,
            buckets=[
                Bucket(id="ai", name="AI", target_pct=Decimal("60"), universe=["NVDA"]),
                Bucket(id="energy", name="Energy", target_pct=Decimal("20"), universe=["XOM"]),
            ],
            risk_overrides={},
        )
        return CompileResult(
            strategy=strategy,
            tickers=[],
            sources=[Source(title="src", url="https://e/x")],
            buckets=[
                CompiledBucket(
                    name="AI",
                    target_pct=Decimal("60"),
                    tickers=[SuggestedTicker(symbol="NVDA", rationale="leader")],
                ),
                CompiledBucket(
                    name="Energy", target_pct=Decimal("20"), tickers=[SuggestedTicker(symbol="XOM")]
                ),
            ],
        )


def test_compile_bucketed_writes_file_and_renders(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))
    monkeypatch.setattr(compile_module, "_build_compiler", lambda settings: FakeBucketedCompiler())
    result = runner.invoke(app, ["compile", "thematic", "--text", "60% AI, 20% energy"])
    assert result.exit_code == 0, result.output
    out = tmp_path / "strategies" / "thematic.yaml"
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "buckets:" in text
    assert "AI" in result.output and "Energy" in result.output  # per-bucket summary
    assert "60" in result.output  # target percent shown


def test_compile_over_allocation_exits_nonzero(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))

    class OverCompiler:
        def compile(self, strategy_id, prose):
            from decimal import Decimal

            from rh_wizard.models.bucket import Bucket

            # Building this Strategy raises ValidationError (Σ target_pct > 100).
            Strategy(
                id=strategy_id,
                name="Over",
                buckets=[
                    Bucket(id="a", name="A", target_pct=Decimal("60")),
                    Bucket(id="b", name="B", target_pct=Decimal("60")),
                ],
            )
            raise AssertionError("unreachable")

    monkeypatch.setattr(compile_module, "_build_compiler", lambda settings: OverCompiler())
    result = runner.invoke(app, ["compile", "over", "--text", "60% A, 60% B"])
    assert result.exit_code != 0
    assert not (tmp_path / "strategies" / "over.yaml").exists()


class FakeEmptyBucketCompiler:
    def compile(self, strategy_id, prose):
        from decimal import Decimal

        from rh_wizard.models.bucket import Bucket
        from rh_wizard.models.compile import CompiledBucket

        strategy = Strategy(
            id=strategy_id,
            name="Sparse",
            intent=prose,
            buckets=[
                Bucket(id="ai", name="AI", target_pct=Decimal("40"), universe=["NVDA"]),
                Bucket(id="rare", name="Rare", target_pct=Decimal("20")),
            ],  # no tickers
            risk_overrides={},
        )
        return CompileResult(
            strategy=strategy,
            tickers=[],
            sources=[],
            buckets=[
                CompiledBucket(
                    name="AI", target_pct=Decimal("40"), tickers=[SuggestedTicker(symbol="NVDA")]
                ),
                CompiledBucket(name="Rare", target_pct=Decimal("20")),
            ],  # no tickers
        )


def test_compile_flags_empty_bucket(monkeypatch, tmp_path):
    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))
    monkeypatch.setattr(
        compile_module, "_build_compiler", lambda settings: FakeEmptyBucketCompiler()
    )
    result = runner.invoke(app, ["compile", "sparse", "--text", "40% AI, 20% rare"])
    assert result.exit_code == 0, result.output
    assert "will sit as cash" in result.output  # empty bucket flagged


@pytest.mark.skipif(
    not (os.environ.get("RH_WIZARD_LIVE") and os.environ.get("OPENAI_API_KEY")),
    reason="live test: needs RH_WIZARD_LIVE=1 and OPENAI_API_KEY",
)
def test_live_compile_emits_buckets(monkeypatch, tmp_path):
    from decimal import Decimal

    from rh_wizard.strategies.registry import StrategyRegistry

    monkeypatch.setenv("RH_WIZARD_HOME", str(tmp_path))
    result = runner.invoke(
        app,
        [
            "compile",
            "live-buckets",
            "--text",
            "10% small-cap rare earth metals, 70% large-cap value stocks, 20% cannabis stocks",
        ],
    )
    assert result.exit_code == 0, result.output
    s = StrategyRegistry(tmp_path / "strategies").load("live-buckets")
    assert len(s.buckets) >= 2  # a real allocation was detected
    assert sum(b.target_pct for b in s.buckets) <= Decimal("100")
    assert all(b.universe for b in s.buckets)  # each bucket got >=1 web-searched ticker
