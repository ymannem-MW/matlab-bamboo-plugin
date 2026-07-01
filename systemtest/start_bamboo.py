"""
Start a local Bamboo instance with the Atlassian SDK.

The script launches `atlas-run` in the background and writes the process ID to
systemtest/artifacts/bamboo.pid. It does not assume that first-run setup is
complete; use probe_bamboo.py to inspect the resulting server state.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "systemtest" / "artifacts"
LOG_FILE = ARTIFACTS / "atlas-run.log"
PID_FILE = ARTIFACTS / "bamboo.pid"


def find_local_maven() -> str | None:
    configured = os.environ.get("MAVEN_CMD")
    if configured:
        return configured

    local_maven = ROOT.parent / ".tools" / "maven" / "bin" / (
        "mvn.cmd" if os.name == "nt" else "mvn"
    )
    if local_maven.is_file():
        return str(local_maven)

    return shutil.which("mvn")


def get_command() -> list[str]:
    atlas_run = shutil.which("atlas-run")
    http_port = os.environ.get("BAMBOO_PORT", "6990")
    context_path = os.environ.get("BAMBOO_CONTEXT_PATH", "/bamboo")
    artifact_threads = os.environ.get("MAVEN_ARTIFACT_THREADS", "16")

    if atlas_run:
        return [
            atlas_run,
            "--server",
            "localhost",
            "--http-port",
            http_port,
            "--context-path",
            context_path,
        ]

    maven = find_local_maven()
    if not maven:
        raise RuntimeError(
            "Could not find atlas-run or mvn. Install Atlassian SDK or set MAVEN_CMD."
        )

    settings = ROOT / "systemtest" / "maven-settings.xml"
    return [
        maven,
        "-s",
        str(settings),
        "-B",
        "-nsu",
        "bamboo:run",
        f"-Dhttp.port={http_port}",
        f"-Dcontext.path={context_path}",
        "-Damps.quick.reload=false",
        f"-Dmaven.artifact.threads={artifact_threads}",
        "-Dmaven.test.skip=true",
    ]


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    command = get_command()

    print("Starting Bamboo with Atlassian SDK:")
    print("  " + " ".join(command))
    print(f"  cwd={ROOT}")
    print(f"  log={LOG_FILE}")

    log_handle = LOG_FILE.open("w", encoding="utf-8", errors="replace")
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )

    PID_FILE.write_text(str(process.pid), encoding="utf-8")
    print(f"Bamboo process started with pid={process.pid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
