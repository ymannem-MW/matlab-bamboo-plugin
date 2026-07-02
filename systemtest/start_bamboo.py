"""
Build the Maven/AMPS command used to start the Bamboo system-test server.
"""

from __future__ import annotations

import os

from systemtest_common import ROOT, find_maven


def get_command() -> list[str]:
    http_port = os.environ.get("BAMBOO_PORT", "6990")
    context_path = os.environ.get("BAMBOO_CONTEXT_PATH", "/bamboo")

    settings = ROOT / "systemtest" / "maven-settings.xml"
    return [
        find_maven(),
        "-s",
        str(settings),
        "-B",
        "bamboo:run",
        f"-Dhttp.port={http_port}",
        f"-Dcontext.path={context_path}",
        "-Damps.quick.reload=false",
        "-DskipTests",
    ]
