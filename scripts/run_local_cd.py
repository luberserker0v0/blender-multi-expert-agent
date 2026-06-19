"""Build local release artifacts matching the GitHub Actions CD workflow."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], *, cwd: Path = REPO_ROOT) -> None:
    print(f"\n> {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=str(cwd), check=True)


def clean_outputs() -> None:
    for path in (REPO_ROOT / "dist", REPO_ROOT / "ui" / "dist"):
        if path.exists():
            shutil.rmtree(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local CD artifact build.")
    parser.add_argument("--no-clean", action="store_true", help="Do not remove existing dist outputs first.")
    args = parser.parse_args()

    if not args.no_clean:
        clean_outputs()

    run([sys.executable, "scripts/check_docs.py"])
    run([sys.executable, "-m", "compileall", "src", "scripts"])

    run([sys.executable, "-m", "pip", "install", "--upgrade", "build"])
    run([sys.executable, "-m", "build"])

    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("npm is required to build UI artifacts")
    run([npm, "run", "lint"], cwd=REPO_ROOT / "ui")
    run([npm, "run", "build"], cwd=REPO_ROOT / "ui")

    print("\nArtifacts:")
    for path in sorted((REPO_ROOT / "dist").glob("*")):
        print(f"- {path.relative_to(REPO_ROOT)}")
    print(f"- {(REPO_ROOT / 'ui' / 'dist').relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
