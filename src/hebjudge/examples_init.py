"""`hebjudge init`: copy the example agents into the current folder (D-46).

After `pip install hebjudge` there is no repository checkout, so the examples (a free toy agent,
the dental-clinic assistant before and after a fix, the store agent) ship inside the package and
are copied out on request. Existing files are never overwritten.
"""

import shutil
from importlib import resources
from pathlib import Path

REPO_EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def examples_source() -> Path:
    """The bundled examples in an installed package, or the repository's own folder."""
    bundled = resources.files("hebjudge") / "_examples"
    if bundled.is_dir():
        return Path(str(bundled))
    return REPO_EXAMPLES


def copy_examples(destination: str | Path = "examples") -> list[Path]:
    """Copy the example files that do not exist yet; return the files written."""
    source = examples_source()
    destination = Path(destination)
    written = []
    for path in sorted(source.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        target = destination / path.relative_to(source)
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        written.append(target)
    return written
