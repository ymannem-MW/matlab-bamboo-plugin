"""
Run the full local/CI Bamboo system-test workflow.
"""

from __future__ import annotations

import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import configure_project
import probe_bamboo
import run_builds
import start_bamboo
from systemtest_common import ARTIFACTS, ROOT
import systemtest_logging as log


LOG_FILE = ARTIFACTS / "bamboo-run.log"
LAUNCHER_FILE = ARTIFACTS / "start-bamboo.cmd"
IS_WINDOWS = sys.platform.startswith("win")


BAMBOO_STARTUP_MILESTONES = (
    re.compile(r"Building jar:"),
    re.compile(r"Starting bamboo"),
    re.compile(r"Deploying web application archive"),
    re.compile(r"Initializing Spring root WebApplicationContext"),
    re.compile(r"Spring context started for bundle: com\.mathworks\.ci\.matlab-bamboo-plugin"),
    re.compile(r"Default Agent.*started"),
    re.compile(r"Bamboo primary node started"),
    re.compile(r"Bamboo license"),
    re.compile(r"bamboo started successfully"),
    re.compile(r"BUILD SUCCESS"),
    re.compile(r"BUILD FAILURE"),
    re.compile(r"\[ERROR\]"),
)


def print_phase_header(message: str) -> None:
    log.section(message)


def print_log_tail(line_count: int = 80) -> None:
    log.print_file_tail(LOG_FILE, line_count)


def cmd_quote(value: Path | str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def write_windows_launcher(command: list[str]) -> None:
    LOG_FILE.write_text("", encoding="utf-8", errors="replace")
    LAUNCHER_FILE.write_text(
        "\r\n".join(
            [
                "@echo off",
                f"cd /d {cmd_quote(ROOT)}",
                f"call {subprocess.list2cmdline(command)} > {cmd_quote(LOG_FILE)} 2>&1",
                "",
            ]
        ),
        encoding="utf-8",
        errors="replace",
    )


def launch_bamboo(command: list[str]) -> tuple[subprocess.Popen, object | None]:
    if IS_WINDOWS:
        write_windows_launcher(command)
        process = subprocess.Popen(
            ["cmd.exe", "/d", "/c", str(LAUNCHER_FILE)],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=(
                subprocess.CREATE_NEW_PROCESS_GROUP
                | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            ),
        )
        return process, None

    log_file = LOG_FILE.open("w", encoding="utf-8", errors="replace")
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        # AMPS treats EOF on stdin as a graceful shutdown request.
        # Keep the pipe open while the system-test driver configures Bamboo.
        stdin=subprocess.PIPE,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    return process, log_file


def stream_bamboo_progress(stop_event: threading.Event, process: subprocess.Popen) -> None:
    position = 0
    started = time.time()
    last_progress = started
    last_milestone = "starting Maven/AMPS"

    while not stop_event.is_set():
        if LOG_FILE.exists():
            with LOG_FILE.open("r", encoding="utf-8", errors="replace") as log_file:
                log_file.seek(position)
                for line in log_file:
                    text = line.strip()
                    if any(pattern.search(text) for pattern in BAMBOO_STARTUP_MILESTONES):
                        last_milestone = text
                        log.info(f"Bamboo milestone: {text}")
                position = log_file.tell()

        now = time.time()
        if now - last_progress >= 30:
            elapsed = int(now - started)
            state = "running" if process.poll() is None else f"exited rc={process.returncode}"
            log.info(
                f"Bamboo startup elapsed={elapsed}s; "
                f"process={state}; last={last_milestone}"
            )
            last_progress = now

        if process.poll() is not None:
            return

        stop_event.wait(2)


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    command = start_bamboo.get_command()
    started = time.time()
    phase = 0

    print_phase_header(f"PHASE {phase}: Start Bamboo")
    phase += 1
    log.step("Building plugin and starting Bamboo with Maven/AMPS")
    log.info("AMPS packages the plugin and deploys it into the local Bamboo test server.")
    log.command(command)
    log.artifact(LOG_FILE)

    log_file_handle = None
    process, log_file_handle = launch_bamboo(command)
    try:
        stop_progress = threading.Event()
        progress_thread = threading.Thread(
            target=stream_bamboo_progress,
            args=(stop_progress, process),
            daemon=True,
        )
        progress_thread.start()

        try:
            print_phase_header(f"PHASE {phase}: Probe Bamboo Bootstrap")
            phase += 1
            probe_bamboo.SERVER_PROCESS = process
            bootstrap_result = probe_bamboo.main()
            if bootstrap_result != 0:
                return bootstrap_result
            stop_progress.set()
            progress_thread.join(timeout=5)

            print_phase_header(f"PHASE {phase}: Configure Bamboo Project And Agent")
            phase += 1
            configure_result = configure_project.main()
            if configure_result != 0:
                return configure_result

            print_phase_header(f"PHASE {phase}: Run MATLAB Bamboo Plans")
            phase += 1
            return run_builds.main()
        except Exception as exc:
            print("")
            log.error(str(exc))
            if process.poll() is not None:
                log.error(f"Bamboo/AMPS process already exited with code {process.returncode}.")
            print_log_tail()
            return 1
        finally:
            stop_progress.set()
            progress_thread.join(timeout=5)
            elapsed = int(time.time() - started)
            print_phase_header(f"PHASE {phase}: Final Bamboo State")
            log.info(f"System-test driver completed after {elapsed}s.")
            if process.poll() is None:
                log.success("Bamboo stayed available for the full system-test run.")
                log.info("The CI runner or container lifecycle will clean up the Bamboo process.")
            else:
                log.warning(f"Bamboo is not running. Process exited with code {process.returncode}.")
            log.artifact(ARTIFACTS)
    finally:
        if log_file_handle is not None:
            log_file_handle.close()


if __name__ == "__main__":
    sys.exit(main())
