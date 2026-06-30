"""
Publish Bamboo Specs for the MATLAB plugin system-test plans.

This is the Bamboo equivalent of the TeamCity REST project setup script. Bamboo
Specs is used for plan creation because it is the supported path for plugin task
configuration.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
SPECS_DIR = ROOT / "systemtest" / "specs"
BAMBOO_URL = os.environ.get("BAMBOO_URL", "http://localhost:6990/bamboo").rstrip("/")
BAMBOO_USERNAME = os.environ.get("BAMBOO_USERNAME", "admin")
BAMBOO_PASSWORD = os.environ.get("BAMBOO_PASSWORD", "admin")
MATLAB_CAPABILITY = os.environ.get("MATLAB_BAMBOO_CAPABILITY", "MATLAB R2026a")


def find_maven() -> str:
    configured = os.environ.get("MAVEN_CMD")
    if configured:
        return configured

    local_maven = ROOT.parent / ".tools" / "maven" / "bin" / (
        "mvn.cmd" if os.name == "nt" else "mvn"
    )
    if local_maven.is_file():
        return str(local_maven)

    maven = shutil.which("mvn")
    if maven:
        return maven

    raise RuntimeError("Could not find Maven. Set MAVEN_CMD or install mvn.")


def detect_matlab_path() -> str:
    configured = os.environ.get("MATLAB_PATH")
    if configured:
        return configured

    matlab = shutil.which("matlab")
    if matlab:
        return str(Path(matlab).resolve().parent.parent)

    windows_default = Path(r"C:\Program Files\MATLAB\R2026a")
    if windows_default.is_dir():
        return str(windows_default)

    raise RuntimeError("Could not find MATLAB. Set MATLAB_PATH or put matlab on PATH.")


def make_session() -> requests.Session:
    print(f"Connecting to Bamboo REST API at {BAMBOO_URL}...")
    session = requests.Session()
    session.auth = (BAMBOO_USERNAME, BAMBOO_PASSWORD)
    session.headers.update({"Accept": "application/json"})
    response = session.get(f"{BAMBOO_URL}/rest/api/latest/server", timeout=30)
    print(f"  REST /server returned HTTP {response.status_code}")
    response.raise_for_status()
    print(f"  Authenticated as '{BAMBOO_USERNAME}'.")
    return session


def configure_matlab_capability() -> None:
    session = make_session()
    matlab_path = detect_matlab_path()
    capability_key = f"system.builder.matlab.{MATLAB_CAPABILITY}"
    print(f"Configuring Bamboo agent capability: {capability_key} = {matlab_path}")

    print("  Reading available Bamboo agents...")
    response = session.get(f"{BAMBOO_URL}/rest/api/latest/agent", timeout=30)
    print(f"  Agent list returned HTTP {response.status_code}")
    response.raise_for_status()
    agents = response.json()
    if not agents:
        raise RuntimeError("Bamboo reported no agents.")

    agent_id = agents[0]["id"]
    agent_name = agents[0].get("name", "<unknown>")
    print(f"  Using agent id={agent_id}, name={agent_name}")
    response = session.post(
        f"{BAMBOO_URL}/rest/api/latest/agent/{agent_id}/capability",
        json={"key": capability_key, "value": matlab_path},
        timeout=30,
    )
    print(f"  Capability update returned HTTP {response.status_code}")
    if response.status_code not in (200, 201, 204):
        raise RuntimeError(
            f"Failed to configure capability on agent {agent_id}: "
            f"HTTP {response.status_code}: {response.text[:300]}"
        )
    print("  Agent capability configured.")


def main() -> int:
    configure_matlab_capability()

    maven = find_maven()
    settings = ROOT / "systemtest" / "maven-settings.xml"
    command = [
        maven,
        "-s",
        str(settings),
        "-B",
        "compile",
        "exec:java",
        "-Dexec.mainClass=com.mathworks.ci.systemtest.BambooSystemTestSpecs",
        "-Dexec.cleanupDaemonThreads=false",
    ]

    print("Publishing Bamboo system-test specs:")
    print("  " + " ".join(command))
    result = subprocess.call(command, cwd=SPECS_DIR)
    print(f"  Specs publish exited with code {result}")
    return result


if __name__ == "__main__":
    sys.exit(main())
