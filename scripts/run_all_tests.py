"""Run the full automated test suite using unittest discovery."""

import argparse
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run all repo tests with unittest discovery.")
    parser.add_argument(
        "--start-directory",
        default="tests",
        help="Directory to start unittest discovery from. Defaults to tests.",
    )
    parser.add_argument(
        "--pattern",
        default="test*.py",
        help="Filename pattern used by unittest discovery. Defaults to test*.py.",
    )
    parser.add_argument(
        "--top-level-directory",
        default=".",
        help="Top-level project directory for unittest discovery. Defaults to repo root.",
    )
    parser.add_argument(
        "--verbosity",
        type=int,
        default=2,
        help="unittest verbosity. Defaults to 2.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    loader = unittest.defaultTestLoader
    suite = loader.discover(
        start_dir=str(REPO_ROOT / args.start_directory),
        pattern=args.pattern,
        top_level_dir=str(REPO_ROOT / args.top_level_directory),
    )
    result = unittest.TextTestRunner(verbosity=args.verbosity).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
