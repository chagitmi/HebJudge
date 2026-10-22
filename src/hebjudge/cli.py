"""Command-line entry point for HebJudge."""

import argparse

from hebjudge import __version__


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="hebjudge",
        description="Hebrew agent evaluation & red-teaming",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.parse_args()
    parser.print_help()


if __name__ == "__main__":
    main()