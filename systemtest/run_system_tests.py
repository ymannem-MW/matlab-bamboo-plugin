"""
Run the full local/CI Bamboo system-test workflow.
"""

from __future__ import annotations

import re
import os
import signal
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import configure_project
import probe_bamboo
import run_builds
import start_bamboo


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "systemtest" / "artifacts"
LOG_FILE = ARTIFACTS / "atlas-run.log"
PID_FILE = ARTIFACTS / "bamboo.pid"
TARGET_DIR = ROOT / "target"
BAMBOO_PORT = os.environ.get("BAMBOO_PORT", "6990")
LAUNCHER_FILE = ARTIFACTS / "start-bamboo.cmd"


LOG_MILESTONES = (
    re.compile(r"--- .* @ matlab-bamboo-plugin ---"),
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
    re.compile(r"ERROR"),
)


def print_phase(message: str) -> None:
    print("")
    print("=" * 60)
    print(message)
    print("=" * 60)


def print_log_tail(line_count: int = 80) -> None:
    if not LOG_FILE.is_file():
        print("No Bamboo/AMPS log file is available yet.")
        return

    lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    print(f"Last {min(line_count, len(lines))} lines from {LOG_FILE}:")
    for line in lines[-line_count:]:
        print(line)


def powershell_quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def rotate_target_directory() -> None:
    if not TARGET_DIR.exists():
        print("  No existing target directory found.")
        return

    stale = ROOT / f"target-stale-{time.strftime('%Y%m%d-%H%M%S')}"
    for attempt in range(1, 7):
        print(f"  Moving existing target directory to {stale.name} (attempt {attempt}/6)")
        try:
            TARGET_DIR.rename(stale)
            print("  Existing target directory moved out of the way.")
            return
        except OSError as exc:
            print(f"  Rename failed: {exc}")
            if attempt < 6:
                print("  Waiting for Bamboo/Windows file locks to release...")
                time.sleep(5)

    print("  Trying to remove target directory directly...")
    try:
        shutil.rmtree(TARGET_DIR)
        print("  Existing target directory removed.")
    except OSError as exc:
        raise RuntimeError(
            "Could not move or remove target. A Windows/OneDrive file lock is "
            f"still holding generated files under {TARGET_DIR}: {exc}"
        ) from exc


def stop_process_tree(pid: int) -> None:
    print(f"  Stopping existing process tree pid={pid}")
    if sys.platform.startswith("win"):
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)
        return

    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except OSError:
        subprocess.run(["kill", "-TERM", str(pid)], check=False)
    time.sleep(5)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except OSError:
        subprocess.run(["kill", "-KILL", str(pid)], check=False)


def stop_pid_file_process() -> None:
    if not PID_FILE.is_file():
        print("  No Bamboo pid file found.")
        return

    pid_text = PID_FILE.read_text(encoding="utf-8").strip()
    if not pid_text:
        print("  Bamboo pid file is empty.")
        PID_FILE.unlink(missing_ok=True)
        return

    stop_process_tree(int(pid_text))
    PID_FILE.unlink(missing_ok=True)


def stop_process_on_port() -> None:
    port = BAMBOO_PORT
    if sys.platform.startswith("win"):
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                f"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue "
                "| Select-Object -ExpandProperty OwningProcess -Unique"
            ),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        pids = [
            int(line.strip())
            for line in result.stdout.splitlines()
            if line.strip().isdigit() and int(line.strip()) > 0
        ]
    else:
        result = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True, check=False)
        pids = [
            int(line.strip())
            for line in result.stdout.splitlines()
            if line.strip().isdigit() and int(line.strip()) > 0
        ]

    if not pids:
        print(f"  No process is listening on port {port}.")
        return

    for pid in pids:
        stop_process_tree(pid)


def teardown_existing_bamboo() -> None:
    print("Closing any existing Bamboo process before starting a new run...")
    stop_pid_file_process()
    stop_process_on_port()
    stop_bamboo_related_processes()
    time.sleep(5)


def stop_bamboo_related_processes() -> None:
    if not sys.platform.startswith("win"):
        return

    patterns = [
        ROOT / "target" / "bamboo",
        ROOT / "target" / "container",
        LAUNCHER_FILE,
        "cargo-bamboo-home",
        "bamboo:run",
    ]
    pattern_values = ", ".join(powershell_quote(pattern) for pattern in patterns)
    script = f"""
$selfPid = $PID
$patterns = @({pattern_values})
Get-CimInstance Win32_Process |
  Where-Object {{
    $cmd = $_.CommandLine
    $name = $_.Name
    $cmd -and
      $_.ProcessId -ne $selfPid -and
      ($name -in @('java.exe', 'cmd.exe', 'mvn.cmd')) -and
      ($patterns | Where-Object {{ $cmd -like "*$_*" }})
  }} |
  ForEach-Object {{
    Write-Output ("  Stopping Bamboo-related process pid={{0}} name={{1}}" -f $_.ProcessId, $_.Name)
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }}
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    output = (result.stdout or "").strip()
    if output:
        print(output)
    if result.returncode != 0:
        error = (result.stderr or "").strip()
        print(f"  Bamboo-related process scan skipped/failed: {error or result.returncode}")


def cmd_quote(value: Path | str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def should_teardown_bamboo() -> bool:
    return os.environ.get("CI_TEARDOWN_BAMBOO", "").lower() in ("1", "true", "yes")


def launch_bamboo(command: list[str]) -> tuple[subprocess.Popen, object | None]:
    if sys.platform.startswith("win") and should_teardown_bamboo():
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
        process = subprocess.Popen(
            ["cmd.exe", "/d", "/c", str(LAUNCHER_FILE)],
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        return process, None

    if sys.platform.startswith("win"):
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
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    return process, log_file


def stop_launched_bamboo(process: subprocess.Popen) -> None:
    if process.stdin:
        try:
            process.stdin.close()
        except OSError:
            pass
        try:
            process.wait(timeout=60)
            return
        except subprocess.TimeoutExpired:
            print("  Bamboo process did not exit after stdin close; stopping process tree.")

    stop_process_tree(process.pid)
    try:
        process.wait(timeout=60)
    except subprocess.TimeoutExpired:
        print("  Bamboo process did not exit after taskkill; forcing one more termination.")
        process.kill()
        process.wait(timeout=30)


def stream_bamboo_progress(stop_event: threading.Event, process: subprocess.Popen) -> None:
    position = 0
    started = time.time()
    last_progress = started
    last_milestone = "starting Maven/AMPS"

    while not stop_event.is_set():
        if LOG_FILE.exists():
            with LOG_FILE.open("r", encoding="utf-8", errors="replace") as log:
                log.seek(position)
                for line in log:
                    text = line.strip()
                    if any(pattern.search(text) for pattern in LOG_MILESTONES):
                        last_milestone = text
                        print(f"[bamboo] {text}")
                position = log.tell()

        now = time.time()
        if now - last_progress >= 30:
            elapsed = int(now - started)
            state = "running" if process.poll() is None else f"exited rc={process.returncode}"
            print(
                f"[progress] Bamboo startup elapsed={elapsed}s; "
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
    teardown_at_end = should_teardown_bamboo()

    print_phase("PHASE 0: Teardown Existing Bamboo")
    teardown_existing_bamboo()

    print_phase("PHASE 1: Prepare Workspace")
    rotate_target_directory()

    print_phase("PHASE 2: Start Bamboo")
    print("  " + " ".join(command))
    print(f"  log={LOG_FILE}")

    log_file_handle = None
    process, log_file_handle = launch_bamboo(command)
    try:
        PID_FILE.write_text(str(process.pid), encoding="utf-8")

        stop_progress = threading.Event()
        progress_thread = threading.Thread(
            target=stream_bamboo_progress,
            args=(stop_progress, process),
            daemon=True,
        )
        progress_thread.start()

        try:
            print_phase("PHASE 3: Probe Bamboo Bootstrap")
            probe_bamboo.SERVER_PROCESS = process
            bootstrap_result = probe_bamboo.main()
            if bootstrap_result != 0:
                return bootstrap_result

            print_phase("PHASE 4: Configure Bamboo Project And Agent")
            configure_result = configure_project.main()
            if configure_result != 0:
                return configure_result

            print_phase("PHASE 5: Run MATLAB Bamboo Plans")
            return run_builds.main()
        except Exception as exc:
            print("")
            print(f"ERROR: {exc}")
            if process.poll() is not None:
                print(f"Bamboo/AMPS process already exited with code {process.returncode}.")
            print_log_tail()
            return 1
        finally:
            stop_progress.set()
            progress_thread.join(timeout=5)
            elapsed = int(time.time() - started)
            print_phase("PHASE 6: Final Bamboo State")
            print(f"System-test driver completed after {elapsed}s.")
            if process.poll() is None:
                if teardown_at_end:
                    print("CI teardown requested; stopping Bamboo before exit.")
                    stop_launched_bamboo(process)
                    PID_FILE.unlink(missing_ok=True)
                else:
                    print(f"Bamboo is still running at: {probe_bamboo.BAMBOO_URL}")
                    print("The next run will close this server before starting a fresh one.")
            else:
                print(f"Bamboo is not running. Process exited with code {process.returncode}.")
            print(f"System-test artifacts are in: {ARTIFACTS}")
    finally:
        if log_file_handle is not None:
            log_file_handle.close()


if __name__ == "__main__":
    sys.exit(main())
