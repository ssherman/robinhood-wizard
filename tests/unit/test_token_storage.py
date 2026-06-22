import json
import stat

from rh_wizard.auth.token_storage import TokenFile


def test_load_missing_returns_none(tmp_path):
    assert TokenFile(tmp_path / "tokens.json").load() is None


def test_save_then_load_roundtrip(tmp_path):
    tf = TokenFile(tmp_path / "tokens.json")
    tf.save({"refresh_token": "r", "access_token": "a"})
    assert tf.load() == {"refresh_token": "r", "access_token": "a"}


def test_save_sets_mode_0600(tmp_path):
    p = tmp_path / "tokens.json"
    TokenFile(p).save({"x": 1})
    assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_save_is_atomic_no_partial_temp_left(tmp_path):
    p = tmp_path / "tokens.json"
    TokenFile(p).save({"x": 1})
    # only the final file remains; no leftover *.tmp
    leftovers = [q.name for q in tmp_path.iterdir() if q.name != "tokens.json"]
    assert leftovers == []


def test_save_overwrites(tmp_path):
    p = tmp_path / "tokens.json"
    tf = TokenFile(p)
    tf.save({"v": 1})
    tf.save({"v": 2})
    assert json.loads(p.read_text())["v"] == 2
