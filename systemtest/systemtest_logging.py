"""
Small logging helpers for the Bamboo system-test driver.

The full AMPS, Maven, REST, and Bamboo payloads are still written to artifacts.
Console output should stay focused on phase progress, decisions, and failures.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import subprocess


WIDTH = 72


def _timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def section(title: str) -> None:
    print("")
    print("=" * WIDTH)
    print(title)
    print("=" * WIDTH)


def step(message: str) -> None:
    print(f"[{_timestamp()}] STEP     {message}")


def info(message: str) -> None:
    print(f"[{_timestamp()}] INFO     {message}")


def detail(message: str) -> None:
    print(f"          {message}")


def success(message: str) -> None:
    print(f"[{_timestamp()}] PASS     {message}")


def warning(message: str) -> None:
    print(f"[{_timestamp()}] WARN     {message}")


def error(message: str) -> None:
    print(f"[{_timestamp()}] ERROR    {message}")


def command(command_line: list[str]) -> None:
    print(f"[{_timestamp()}] COMMAND  {subprocess.list2cmdline(command_line)}")


def artifact(path: Path) -> None:
    print(f"[{_timestamp()}] ARTIFACT {path}")


def print_file_tail(path: Path, line_count: int = 80) -> None:
    if not path.is_file():
        warning(f"No log file is available yet: {path}")
        return

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    print(f"Last {min(line_count, len(lines))} lines from {path}:")
    for line in lines[-line_count:]:
        print(line)


def write_text_artifact(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", errors="replace")
    artifact(path)
    return path


def summarize_lines(
    text: str,
    patterns: tuple[re.Pattern[str], ...],
    max_lines: int = 80,
) -> list[str]:
    matches: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and any(pattern.search(stripped) for pattern in patterns):
            matches.append(stripped)
    return matches[-max_lines:]
