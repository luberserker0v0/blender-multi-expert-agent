"""Run the same baseline checks as GitHub Actions CI."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], *, cwd: Path = REPO_ROOT, env: dict[str, str] | None = None) -> None:
    print(f"\n> {' '.join(command)}", flush=True)
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    subprocess.run(command, cwd=str(cwd), env=merged_env, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local CI checks.")
    parser.add_argument("--skip-python", action="store_true", help="Skip Python compile and unit tests.")
    parser.add_argument("--skip-ui", action="store_true", help="Skip UI unit tests and build.")
    parser.add_argument("--skip-e2e", action="store_true", help="Skip Playwright mock e2e.")
    args = parser.parse_args()

    if not args.skip_python:
        run([sys.executable, "-m", "compileall", "src", "scripts"])
        run(
            [sys.executable, "-m", "pytest", "tests/unit", "-q"],
            env={"PYTHONPATH": str(REPO_ROOT / "src")},
        )

    npm = shutil.which("npm")
    if not npm and not args.skip_ui:
        raise RuntimeError("npm is required for UI CI checks")

    ui_dir = REPO_ROOT / "ui"
    if not args.skip_ui:
        run([npm, "test"], cwd=ui_dir)
        run([npm, "run", "build"], cwd=ui_dir)

    if not args.skip_e2e:
        if not npm:
            raise RuntimeError("npm is required for Playwright e2e checks")
        run([npm, "run", "test:e2e"], cwd=ui_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
