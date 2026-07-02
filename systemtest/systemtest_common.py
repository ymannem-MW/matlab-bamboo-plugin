"""
Shared helpers for Bamboo system-test scripts.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYSTEMTEST_DIR = ROOT / "systemtest"
ARTIFACTS = SYSTEMTEST_DIR / "artifacts"


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

    raise RuntimeError("Could not find Maven. Install mvn or set MAVEN_CMD.")
