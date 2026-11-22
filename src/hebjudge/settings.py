"""User settings: the OpenAI API key for the judge, kept outside any project folder (D-46).

The key is looked up, in order: the environment, a `.env` file in the current folder (as in v1),
and the user's settings file `~/.hebjudge/config.env`, which the UI writes. The key is never
sent back to the page in full, never logged, and never stored in a project or a trace.
"""

import os
import re
import stat
from pathlib import Path

from dotenv import load_dotenv

KEY_NAME = "OPENAI_API_KEY"
KEY_PATTERN = re.compile(r"^sk-[A-Za-z0-9_\-]{20,}$")


def config_dir() -> Path:
    return Path(os.environ.get("HEBJUDGE_HOME") or Path.home() / ".hebjudge")


def config_file() -> Path:
    return config_dir() / "config.env"


def load_settings() -> None:
    """Load `.env` from the current folder, then the user's settings file; never override.

    The path is given explicitly: without it, python-dotenv searches upward from this module's
    own location, which would read a repository's `.env` even when running elsewhere.
    """
    load_dotenv(Path.cwd() / ".env")
    if config_file().is_file():
        load_dotenv(config_file(), override=False)


def key_status() -> dict:
    """Whether a key is available and where it comes from; only its last 4 characters."""
    key = os.environ.get(KEY_NAME, "")
    in_file = _read_file_key()
    if key:
        source = "file" if key == in_file else "environment"
        return {"set": True, "source": source, "hint": key[-4:], "file": str(config_file())}
    return {"set": False, "source": None, "hint": None, "file": str(config_file())}


def save_api_key(key: str) -> None:
    key = key.strip()
    if not KEY_PATTERN.match(key):
        raise ValueError("this does not look like an OpenAI API key (it starts with sk-)")
    _write_file_key(key)
    os.environ[KEY_NAME] = key


def delete_api_key() -> None:
    if _read_file_key() is not None and os.environ.get(KEY_NAME) == _read_file_key():
        os.environ.pop(KEY_NAME, None)
    _write_file_key(None)


def test_api_key() -> tuple[bool, str]:
    """Check the key with a free call (listing models); nothing is billed."""
    from openai import OpenAI

    if not os.environ.get(KEY_NAME):
        return False, "no key is set"
    try:
        OpenAI(max_retries=0, timeout=15).models.list()
    except Exception as exc:  # report any failure to the user, in short
        return False, type(exc).__name__
    return True, "ok"


def _read_file_key() -> str | None:
    path = config_file()
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == KEY_NAME:
            return value.strip().strip('"') or None
    return None


def _write_file_key(key: str | None) -> None:
    path = config_file()
    lines = []
    if path.is_file():
        lines = [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.partition("=")[0].strip() != KEY_NAME
        ]
    if key is not None:
        lines.append(f"{KEY_NAME}={key}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # readable by the user only, where supported
    except OSError:
        pass
