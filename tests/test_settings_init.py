"""Tests for the API-key settings and `hebjudge init` (D-46). Offline; nothing touches the real home.

Assertions compare only whether a key is set and its last characters, never the key itself, so
a failure can never print a real key from the developer's machine.
"""

import os
import stat
import sys

import pytest

from hebjudge import settings
from hebjudge.cli import main
from hebjudge.examples_init import copy_examples, examples_source

GOOD_KEY = "sk-test" + "a" * 40


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HEBJUDGE_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)


def test_no_key_at_first():
    status = settings.key_status()
    assert status["set"] is False and status["hint"] is None


def test_save_shows_only_the_last_characters():
    settings.save_api_key(f"  {GOOD_KEY}  ")
    status = settings.key_status()
    assert status == {**status, "set": True, "source": "file", "hint": GOOD_KEY[-4:]}
    assert GOOD_KEY not in str(status)
    assert os.environ.get("OPENAI_API_KEY") == GOOD_KEY, "the saved key was not loaded"


def test_invalid_key_is_rejected():
    with pytest.raises(ValueError, match="sk-"):
        settings.save_api_key("not-a-key")
    assert not settings.config_file().exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_settings_file_is_private():
    settings.save_api_key(GOOD_KEY)
    mode = stat.S_IMODE(settings.config_file().stat().st_mode)
    assert mode == 0o600


def test_load_settings_reads_the_file_but_does_not_override(monkeypatch):
    settings.save_api_key(GOOD_KEY)
    monkeypatch.delenv("OPENAI_API_KEY")
    settings.load_settings()
    assert settings.key_status()["hint"] == GOOD_KEY[-4:]
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-environment" + "b" * 30)
    settings.load_settings()
    assert settings.key_status()["source"] == "environment"


def test_delete_keeps_other_settings():
    settings.config_dir().mkdir(parents=True)
    settings.config_file().write_text("OTHER=1\n", encoding="utf-8")
    settings.save_api_key(GOOD_KEY)
    settings.delete_api_key()
    assert settings.config_file().read_text(encoding="utf-8") == "OTHER=1\n"
    assert settings.key_status()["set"] is False


def test_key_test_without_a_key():
    assert settings.test_api_key() == (False, "no key is set")


def test_cli_key_show(capsys):
    assert main(["key"]) == 0
    assert "No key is set" in capsys.readouterr().out


# --- examples ------------------------------------------------------------------


def test_examples_are_available():
    assert (examples_source() / "targets" / "toy-python.yaml").is_file()
    assert (examples_source() / "toy_agent.py").is_file()


def test_copy_examples_never_overwrites(tmp_path):
    written = copy_examples(tmp_path / "examples")
    assert any(p.name == "toy-python.yaml" for p in written)
    toy = tmp_path / "examples" / "toy_agent.py"
    toy.write_text("# changed by the user\n", encoding="utf-8")
    assert copy_examples(tmp_path / "examples") == []
    assert toy.read_text(encoding="utf-8") == "# changed by the user\n"


def test_cli_init_then_toy_agent_works(capsys):
    assert main(["init"]) == 0
    assert "Copied" in capsys.readouterr().out
    assert main(["target", "test", "examples/targets/toy-python.yaml"]) == 0
    assert "עוזר לדוגמה" in capsys.readouterr().out


def test_a_dotenv_elsewhere_is_not_read(tmp_path, monkeypatch):
    """Only the current folder's .env counts, not one found by searching upward."""
    (tmp_path / "project").mkdir()
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-parent" + "c" * 30 + "\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path / "project")
    settings.load_settings()
    assert settings.key_status()["set"] is False
