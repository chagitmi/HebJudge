"""Check that a built wheel contains every source module and the files the tool needs (D-46).

Guards against packaging mistakes, such as an ignore rule that silently drops a folder.

Usage: python scripts/check_wheel.py dist/hebjudge-*.whl
"""

import sys
import zipfile
from pathlib import Path

REQUIRED = [
    "hebjudge/ui/static/index.html",
    "hebjudge/ui/static/app.js",
    "hebjudge/ui/static/fonts/plex-hebrew-400.woff2",
    "hebjudge/_examples/targets/toy-python.yaml",
    "hebjudge/_examples/toy_agent.py",
]


def main() -> int:
    wheel = Path(sys.argv[1])
    names = set(zipfile.ZipFile(wheel).namelist())
    source = Path(__file__).resolve().parents[1] / "src"
    expected = {p.relative_to(source).as_posix() for p in source.rglob("*.py")}
    expected |= {
        p.relative_to(source).as_posix() for p in (source / "hebjudge/template_data").glob("*.yaml")
    }
    missing = sorted((expected | set(REQUIRED)) - names)
    if missing:
        print(f"{wheel.name} is missing {len(missing)} files:")
        for name in missing:
            print(f"  {name}")
        return 1
    print(f"{wheel.name}: all {len(expected) + len(REQUIRED)} expected files are present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
