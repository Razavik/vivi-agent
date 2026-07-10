from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


def _relaunch_under_venv(argv: list[str]) -> int | None:
    if not VENV_PYTHON.exists():
        return None
    current = Path(sys.executable).resolve()
    if current == VENV_PYTHON.resolve():
        return None
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    result = subprocess.run([str(VENV_PYTHON), str(Path(__file__).resolve()), *argv], cwd=ROOT, env=env)
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Start Vivi backend server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload on file changes (default)")
    parser.add_argument("--no-reload", action="store_true", help="Disable auto-reload")
    args = parser.parse_args()

    relaunch_code = _relaunch_under_venv(sys.argv[1:])
    if relaunch_code is not None:
        return relaunch_code

    try:
        import uvicorn
    except ImportError as exc:
        print("uvicorn is not installed in the current Python environment.")
        print("Install dependencies with: pip install -r requirements.txt")
        return 1

    if args.no_reload:
        reload_enabled = False
    else:
        reload_enabled = True
    
    print(f"Starting backend on http://{args.host}:{args.port} (reload={'enabled' if reload_enabled else 'disabled'})")
    uvicorn.run(
        "src.web.asgi:app",
        host=args.host,
        port=args.port,
        reload=reload_enabled,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
