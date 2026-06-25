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
