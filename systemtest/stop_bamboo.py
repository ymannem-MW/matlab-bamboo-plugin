"""
Stop a Bamboo process started by start_bamboo.py.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PID_FILE = ROOT / "systemtest" / "artifacts" / "bamboo.pid"


def stop_process(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    time.sleep(10)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def main() -> int:
    if not PID_FILE.is_file():
        print("No Bamboo pid file found.")
        return 0

    pid_text = PID_FILE.read_text(encoding="utf-8").strip()
    if not pid_text:
        print("Bamboo pid file is empty.")
        return 0

    pid = int(pid_text)
    print(f"Stopping Bamboo pid={pid}")
    stop_process(pid)
    PID_FILE.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

