"""Start the full dev environment: Python UI bridge + Vite frontend.

Usage:
    python scripts/run_dev.py

Starts both the Python API bridge (default http://127.0.0.1:8765 /
ws://127.0.0.1:8766) and the React Vite dev server
(default http://127.0.0.1:5173) as subprocesses.  Ctrl+C stops both.

Environment variables:
    PYTHON_EXECUTABLE  If set, overrides the Python interpreter used for
                       the bridge and spawned pipeline processes.  Useful when
                       the base conda environment lacks packages (e.g. mcp)
                       that are available in another environment.
    AI3D_DEV_UI_PORT   Vite dev server port. Default: 5173.
    AI3D_UI_BRIDGE_HTTP_PORT
                       Python bridge HTTP port. Default: 8765.
    AI3D_UI_BRIDGE_WS_PORT
                       Python bridge WebSocket port. Default: 8766.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
UI_DIR = REPO_ROOT / "ui"
BRIDGE_SCRIPT = REPO_ROOT / "scripts" / "run_ui_bridge.py"
NPM_CMD = "npm.cmd" if sys.platform == "win32" else "npm"
MIN_PYTHON = (3, 10)
DEFAULT_BRIDGE_HTTP_PORT = "8765"
DEFAULT_BRIDGE_WS_PORT = "8766"
DEFAULT_UI_PORT = "5173"


def _python_version(executable: str) -> tuple[int, int, int] | None:
    try:
        result = subprocess.run(
            [
                executable,
                "-c",
                "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    parts = result.stdout.strip().split(".")
    if len(parts) < 2:
        return None
    try:
        major = int(parts[0])
        minor = int(parts[1])
        micro = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        return None
    return major, minor, micro


def _codex_runtime_python_candidate() -> str:
    home = Path.home()
    return str(
        home
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "python"
        / ("python.exe" if sys.platform == "win32" else "bin/python")
    )


def _resolve_bridge_python() -> str:
    explicit = os.environ.get("PYTHON_EXECUTABLE", "").strip()
    candidates = [
        explicit,
        sys.executable,
        shutil.which("python3.12") or "",
        shutil.which("python3.11") or "",
        shutil.which("python3.10") or "",
        shutil.which("python3") or "",
        _codex_runtime_python_candidate(),
    ]
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        version = _python_version(candidate)
        if version is None:
            continue
        if version[:2] >= MIN_PYTHON:
            if candidate != sys.executable:
                print(
                    "[dev] using Python "
                    f"{version[0]}.{version[1]}.{version[2]} for bridge: {candidate}"
                )
            return candidate

    current = ".".join(str(part) for part in sys.version_info[:3])
    print(
        "[dev] Python 3.10+ is required for the UI bridge and MCP SDK. "
        f"Current interpreter is Python {current}: {sys.executable}\n"
        "[dev] Set PYTHON_EXECUTABLE to a Python 3.10+ interpreter, "
        "or install Python 3.10+ and rerun make run-dev.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def _check_npm_install() -> bool:
    """Run ``npm install`` if ``node_modules`` is missing.  Returns
    ``True`` on success."""
    if (UI_DIR / "node_modules").is_dir():
        return True
    print("[dev] node_modules/ missing — running 'npm install'...")
    result = subprocess.run(
        [NPM_CMD, "install"],
        cwd=str(UI_DIR),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[dev] npm install failed:\n{result.stderr}", file=sys.stderr)
        return False
    print("[dev] npm install completed.")
    return True


def main() -> int:
    # ── validate prerequisites ────────────────────────────────────────
    if not BRIDGE_SCRIPT.is_file():
        print(f"[dev] bridge script not found: {BRIDGE_SCRIPT}", file=sys.stderr)
        return 1

    if not (UI_DIR / "package.json").is_file():
        print(f"[dev] ui/package.json not found — did you clone the ui submodule?", file=sys.stderr)
        return 1

    if not _check_npm_install():
        return 1

    # Check that npm is actually on PATH
    if not shutil.which(NPM_CMD):
        print(f"[dev] '{NPM_CMD}' not found — is Node.js installed and on PATH?", file=sys.stderr)
        return 1

    # ── spawn subprocesses ────────────────────────────────────────────
    python_exe = _resolve_bridge_python()
    bridge_http_port = os.environ.get("AI3D_UI_BRIDGE_HTTP_PORT", DEFAULT_BRIDGE_HTTP_PORT).strip() or DEFAULT_BRIDGE_HTTP_PORT
    bridge_ws_port = os.environ.get("AI3D_UI_BRIDGE_WS_PORT", DEFAULT_BRIDGE_WS_PORT).strip() or DEFAULT_BRIDGE_WS_PORT
    ui_port = os.environ.get("AI3D_DEV_UI_PORT", DEFAULT_UI_PORT).strip() or DEFAULT_UI_PORT
    bridge_http_origin = f"http://127.0.0.1:{bridge_http_port}"
    bridge_ws_origin = f"ws://127.0.0.1:{bridge_ws_port}"
    ui_origin = f"http://127.0.0.1:{ui_port}"
    processes: list[subprocess.Popen] = []

    try:
        # 1. Python bridge
        bridge_env = os.environ.copy()
        bridge_env["AI3D_UI_BRIDGE_HTTP_PORT"] = bridge_http_port
        bridge_env["AI3D_UI_BRIDGE_WS_PORT"] = bridge_ws_port
        bridge_proc = subprocess.Popen(
            [python_exe, str(BRIDGE_SCRIPT)],
            cwd=str(REPO_ROOT),
            env=bridge_env,
        )
        processes.append(bridge_proc)
        print(f"[dev] UI bridge started ({bridge_http_origin}, {bridge_ws_origin})")

        # 2. Vite dev server
        vite_env = os.environ.copy()
        vite_env["VITE_BRIDGE_HTTP_ORIGIN"] = bridge_http_origin
        vite_env["VITE_BRIDGE_WS_ORIGIN"] = bridge_ws_origin
        vite_env["VITE_ACTIVITY_SOCKET_URL"] = f"{bridge_ws_origin}/ws/activity"
        vite_proc = subprocess.Popen(
            [NPM_CMD, "run", "dev", "--", "--host", "127.0.0.1", "--port", ui_port],
            cwd=str(UI_DIR),
            env=vite_env,
        )
        processes.append(vite_proc)
        print(f"[dev] Vite dev server starting ({ui_origin})")
        print("[dev] AO readiness is verified from the UI Settings panel or automatically on session entry.")
        print("[dev] Press Ctrl+C to stop both.")

        # Wait until either process exits
        while all(p.poll() is None for p in processes):
            try:
                for p in processes:
                    p.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                continue
            break

    except KeyboardInterrupt:
        pass
    except FileNotFoundError as exc:
        print(f"[dev] ERROR: {exc}", file=sys.stderr)
        print("[dev] Make sure Node.js is installed and 'npm' is in your PATH.")
        return 1
    finally:
        if processes:
            print("\n[dev] Shutting down...")
            for p in processes:
                if p.poll() is None:
                    p.terminate()
            for p in processes:
                try:
                    p.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    p.kill()
            print("[dev] All processes stopped.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
