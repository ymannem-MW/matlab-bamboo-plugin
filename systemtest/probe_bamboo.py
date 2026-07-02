"""
Probe a freshly started Bamboo instance.

This script intentionally does not assume that Bamboo setup is already complete.
It records redirects, setup pages, REST readiness, plugin state, and the optional
MATLAB executable path. If Bamboo is blocked on setup/licensing, the script
exits with a clear diagnostic instead of pretending the full system test ran.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from systemtest_common import ARTIFACTS
import systemtest_logging as log


BAMBOO_URL = os.environ.get("BAMBOO_URL", "http://localhost:6990/bamboo").rstrip("/")
BAMBOO_USERNAME = os.environ.get("BAMBOO_USERNAME", "admin")
BAMBOO_PASSWORD = os.environ.get("BAMBOO_PASSWORD", "admin")
SERVER_TIMEOUT = int(os.environ.get("BAMBOO_SERVER_TIMEOUT", "900"))
POLL_INTERVAL = int(os.environ.get("BAMBOO_POLL_INTERVAL", "10"))
SERVER_PROCESS: subprocess.Popen | None = None


def summarize_exception(exc: Exception, max_length: int = 180) -> str:
    message = str(exc).replace("\n", " ")
    if len(message) <= max_length:
        return message
    return message[: max_length - 3] + "..."


def save_response(name: str, response: requests.Response, announce: bool = True) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)
    path = ARTIFACTS / safe_name
    path.write_text(
        "\n".join(
            [
                f"URL: {response.url}",
                f"Status: {response.status_code}",
                f"Headers: {dict(response.headers)}",
                "",
                response.text,
            ]
        ),
        encoding="utf-8",
        errors="replace",
    )
    if announce:
        log.artifact(path)


def wait_for_http(deadline: float) -> requests.Response:
    log.step(f"Waiting up to {SERVER_TIMEOUT}s for Bamboo HTTP at {BAMBOO_URL}")
    start = time.time()
    last_progress = start
    last_error = None
    while time.time() < deadline:
        if SERVER_PROCESS is not None and SERVER_PROCESS.poll() is not None:
            raise RuntimeError(
                f"Bamboo process exited before HTTP became ready "
                f"(exit code {SERVER_PROCESS.returncode})."
            )
        try:
            response = requests.get(BAMBOO_URL, timeout=10, allow_redirects=False)
            elapsed = int(time.time() - start)
            log.success(f"Bamboo responded: HTTP {response.status_code} after {elapsed}s")
            return response
        except requests.RequestException as exc:
            last_error = exc
            now = time.time()
            if now - last_progress >= 30:
                elapsed = int(now - start)
                log.info(f"Still waiting for Bamboo HTTP ({elapsed}s elapsed): {summarize_exception(exc)}")
                last_progress = now
            time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"Bamboo did not respond within {SERVER_TIMEOUT}s: {last_error}")


def detect_matlab_path() -> str | None:
    env_path = os.environ.get("MATLAB_PATH")
    if env_path:
        return env_path
    matlab = shutil.which("matlab")
    if not matlab:
        return None
    bin_dir = Path(matlab).resolve().parent
    return str(bin_dir.parent)


def get_rest_server(session: requests.Session) -> requests.Response:
    return session.get(
        urljoin(BAMBOO_URL + "/", "rest/api/latest/server"),
        timeout=20,
        headers={"Accept": "application/json"},
    )


def wait_for_api_ready(deadline: float) -> bool:
    log.step("Checking Bamboo REST API readiness")
    session = requests.Session()
    session.auth = (BAMBOO_USERNAME, BAMBOO_PASSWORD)
    log.info(f"Authenticating as '{BAMBOO_USERNAME}'")

    last_progress = time.time()
    last_status = "<not checked>"
    last_error = None
    while time.time() < deadline:
        if SERVER_PROCESS is not None and SERVER_PROCESS.poll() is not None:
            raise RuntimeError(
                f"Bamboo process exited before REST became ready "
                f"(exit code {SERVER_PROCESS.returncode})."
            )

        try:
            response = get_rest_server(session)
            last_status = f"HTTP {response.status_code}"
            save_response("rest-server.txt", response, announce=response.status_code == 200)

            if response.status_code == 200:
                log.info(f"REST /server returned HTTP {response.status_code}")
                log.success("REST API is ready with configured credentials.")
                return True

            now = time.time()
            if now - last_progress >= 30:
                if response.status_code in (401, 403):
                    log.info("REST API is reachable, but admin credentials are not accepted yet.")
                elif response.status_code in (302, 303):
                    log.info(f"REST API redirected to: {response.headers.get('Location', '')}")
                else:
                    log.info(f"REST /server returned HTTP {response.status_code}; still waiting.")
                last_progress = now
        except requests.RequestException as exc:
            last_error = exc
            now = time.time()
            if now - last_progress >= 30:
                log.info(f"Still waiting for Bamboo REST API: {summarize_exception(exc)}")
                last_progress = now

        time.sleep(POLL_INTERVAL)

    if last_error is not None:
        log.warning(f"Bamboo REST API did not become ready: {summarize_exception(last_error)}")
    else:
        log.warning(f"Bamboo REST API did not become ready; last status was {last_status}.")
    return False


def inspect_landing_page(initial_response: requests.Response) -> None:
    response = initial_response
    if response.status_code in (301, 302, 303, 307, 308):
        location = response.headers.get("Location", "")
        log.info(f"Landing page redirected to: {location}")
        next_url = urljoin(BAMBOO_URL + "/", location)
        try:
            response = requests.get(next_url, timeout=20, allow_redirects=False)
        except requests.RequestException as exc:
            log.warning(f"Landing page capture skipped: {exc}")
            return

    save_response("landing-page.html", response)
    text = response.text.lower()
    title_match = re.search(r"<title>(.*?)</title>", response.text, re.IGNORECASE | re.DOTALL)
    title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else "<unknown>"
    signals = {
        "title": title,
        "dashboard": "build dashboard" in text,
        "setup_complete": "installation and the setup of bamboo is complete" in text,
        "setup_wizard": any(
            phrase in text
            for phrase in (
                "setup wizard",
                "set up bamboo",
                "setup administrator",
                "create administrator",
            )
        ),
        "evaluation_license": "evaluation license" in text,
        "login_link": "userlogin.action" in text,
    }
    log.info("Landing page signals:")
    for key, value in signals.items():
        log.detail(f"{key}: {value}")


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    matlab_path = detect_matlab_path()
    log.info(f"BAMBOO_URL = {BAMBOO_URL}")
    log.info(f"MATLAB_PATH = {matlab_path or '<not found>'}")

    startup_deadline = time.time() + SERVER_TIMEOUT

    response = wait_for_http(startup_deadline)
    inspect_landing_page(response)

    if wait_for_api_ready(startup_deadline):
        log.success("Bamboo bootstrap probe passed: API is available.")
        return 0

    print("")
    log.error("Bamboo bootstrap is not complete.")
    log.info("Review landing-page.html and rest-server.txt to identify the setup/license blocker.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
