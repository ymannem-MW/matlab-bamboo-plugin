"""
Trigger Bamboo system-test plans and validate the results.
"""

from __future__ import annotations

import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import systemtest_logging as log


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "systemtest" / "artifacts"
BAMBOO_URL = os.environ.get("BAMBOO_URL", "http://localhost:6990/bamboo").rstrip("/")
BAMBOO_USERNAME = os.environ.get("BAMBOO_USERNAME", "admin")
BAMBOO_PASSWORD = os.environ.get("BAMBOO_PASSWORD", "admin")
BUILD_TIMEOUT = int(os.environ.get("BAMBOO_BUILD_TIMEOUT", "900"))
POLL_INTERVAL = int(os.environ.get("BAMBOO_BUILD_POLL_INTERVAL", "15"))

PLANS = [
    {
        "key": "MSYS-CMD",
        "name": "MATLAB Command",
        "expected_log": "hello from MATLAB",
    },
    {
        "key": "MSYS-BLD",
        "name": "MATLAB Build",
        "expected_log": "Build Successful",
    },
    {
        "key": "MSYS-TST",
        "name": "MATLAB Tests",
        "junit_artifact": "matlab-artifacts/test-reports/junit.xml",
    },
]


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def write_text_artifact(name: str, text: str, announce: bool = True) -> Path:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS / safe_name(name)
    path.write_text(text, encoding="utf-8", errors="replace")
    if announce:
        log.artifact(path)
    return path


def make_session() -> requests.Session:
    session = requests.Session()
    session.auth = (BAMBOO_USERNAME, BAMBOO_PASSWORD)
    session.headers.update({"Accept": "application/json"})
    response = session.get(urljoin(BAMBOO_URL + "/", "rest/api/latest/server"), timeout=30)
    if response.status_code != 200:
        raise RuntimeError(
            f"Bamboo authentication/readiness failed: HTTP {response.status_code}: {response.text[:300]}"
        )
    log.success("Bamboo REST authentication verified.")
    return session


def trigger_plan(session: requests.Session, plan_key: str) -> str:
    log.step(f"Queueing plan {plan_key}")
    response = session.post(
        urljoin(BAMBOO_URL + "/", f"rest/api/latest/queue/{plan_key}"),
        headers={"Accept": "application/json"},
        timeout=30,
    )
    log.info(f"Queue {plan_key}: HTTP {response.status_code}")
    write_text_artifact(f"queue-{plan_key}.json", response.text)
    if response.status_code not in (200, 201):
        raise RuntimeError(f"Failed to queue {plan_key}: {response.text[:500]}")
    data = response.json()
    result_key = data.get("buildResultKey") or data.get("planResultKey", {}).get("key")
    log.info(f"Queued result key: {result_key}")
    if result_key:
        log.detail(f"Result URL: {BAMBOO_URL}/browse/{result_key}")
    return result_key


def get_result(session: requests.Session, result_key: str) -> dict:
    response = session.get(
        urljoin(BAMBOO_URL + "/", f"rest/api/latest/result/{result_key}"),
        params={"expand": "stages.stage.results.result,artifacts"},
        timeout=30,
    )
    write_text_artifact(f"result-{result_key}.json", response.text, announce=False)
    if response.status_code != 200:
        raise RuntimeError(f"Could not read result {result_key}: {response.status_code}: {response.text[:500]}")
    return response.json()


def wait_for_result(session: requests.Session, result_key: str) -> dict:
    deadline = time.time() + BUILD_TIMEOUT
    start = time.time()
    while time.time() < deadline:
        data = get_result(session, result_key)
        state = data.get("buildState") or data.get("lifeCycleState") or "Unknown"
        finished = data.get("buildCompleted") or state in ("Successful", "Failed", "Error")
        elapsed = int(time.time() - start)
        log.info(f"{result_key}: state={state}, completed={finished}, elapsed={elapsed}s")
        if finished:
            return data
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"Timed out waiting for {result_key}")


def download_log(session: requests.Session, result_key: str) -> str:
    log.step(f"Downloading build log for {result_key}")
    candidates = [
        f"download/{result_key}/build_logs/{result_key}.log",
        f"browse/{result_key}/log",
        f"downloadBuildLog.action?buildKey={result_key}",
    ]
    for candidate in candidates:
        response = session.get(urljoin(BAMBOO_URL + "/", candidate), timeout=60)
        log.detail(f"{candidate}: HTTP {response.status_code}")
        if response.status_code == 200 and response.text.strip():
            write_text_artifact(f"log-{result_key}.txt", response.text)
            return response.text
    write_text_artifact(f"log-{result_key}.txt", "<log download unavailable>")
    return ""


def find_job_result_keys(result: dict) -> list[str]:
    keys: list[str] = []
    stages = result.get("stages", {}).get("stage", [])
    if isinstance(stages, dict):
        stages = [stages]
    for stage in stages:
        job_results = stage.get("results", {}).get("result", [])
        if isinstance(job_results, dict):
            job_results = [job_results]
        for job_result in job_results:
            key = job_result.get("key") or job_result.get("buildResultKey")
            if key:
                keys.append(key)
    return keys


def download_junit(session: requests.Session, result: dict, relative_path: str) -> bytes | None:
    log.step(f"Downloading JUnit artifact: {relative_path}")
    artifacts = result.get("artifacts", {}).get("artifact", [])
    if isinstance(artifacts, dict):
        artifacts = [artifacts]
    log.info(f"Bamboo reported {len(artifacts)} artifact link(s).")
    for artifact in artifacts:
        link = artifact.get("link", {}).get("href")
        if not link:
            continue
        parsed = urlparse(link)
        artifact_url = urljoin(BAMBOO_URL + "/", parsed.path.lstrip("/"))
        response = session.get(artifact_url, timeout=60)
        log.detail(f"artifact link {artifact_url}: HTTP {response.status_code}")
        if response.status_code == 200 and response.content:
            path = ARTIFACTS / "junit.xml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(response.content)
            log.artifact(path)
            return response.content

    result_keys = [result.get("key")] + find_job_result_keys(result)
    for result_key in [key for key in result_keys if key]:
        artifact_name = "MATLAB-Test-Artifacts"
        candidates = [
            f"rest/api/latest/result/{result_key}/artifact/shared/{artifact_name}/{relative_path}",
            f"browse/{result_key}/artifact/shared/{artifact_name}/{Path(relative_path).name}",
            f"download/{result_key}/artifact/shared/{artifact_name}/{Path(relative_path).name}",
        ]
        for candidate in candidates:
            response = session.get(urljoin(BAMBOO_URL + "/", candidate), timeout=60)
            log.detail(f"fallback {candidate}: HTTP {response.status_code}")
            if response.status_code == 200 and response.content:
                path = ARTIFACTS / "junit.xml"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(response.content)
                log.artifact(path)
                return response.content
    return None


def validate_junit(content: bytes) -> str:
    root = ET.fromstring(content)
    if root.tag not in ("testsuites", "testsuite"):
        raise AssertionError(f"Unexpected JUnit root element: {root.tag}")
    return f"Valid JUnit XML root={root.tag}"


def run_and_validate(session: requests.Session, plan: dict) -> bool:
    log.section(f"PLAN: {plan['name']} ({plan['key']})")

    result_key = trigger_plan(session, plan["key"])
    if not result_key:
        raise RuntimeError(f"Bamboo did not return a build result key for {plan['key']}")

    result = wait_for_result(session, result_key)
    state = result.get("buildState")
    log.info(f"Final buildState={state}")
    build_log = download_log(session, result_key)

    if state != "Successful":
        log.error(f"buildState={state}")
        if build_log:
            print(f"Build log tail:\n{build_log[-500:]}")
        return False

    expected_log = plan.get("expected_log")
    if expected_log and expected_log not in build_log:
        log.error(f"log does not contain {expected_log!r}")
        if build_log:
            print(f"Build log tail:\n{build_log[-500:]}")
        return False
    if expected_log:
        log.success(f"log contains {expected_log!r}")

    junit_artifact = plan.get("junit_artifact")
    if junit_artifact:
        content = download_junit(session, result, junit_artifact)
        if content is None:
            log.error(f"could not download {junit_artifact}")
            return False
        log.success(validate_junit(content))
    else:
        log.success("Plan validation passed.")

    return True


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    log.section("SYSTEM TEST: End-to-End Bamboo Plan Validation")
    log.info(f"BAMBOO_URL = {BAMBOO_URL}")
    log.artifact(ARTIFACTS)
    session = make_session()
    results: dict[str, str] = {}

    for plan in PLANS:
        try:
            passed = run_and_validate(session, plan)
        except Exception as exc:
            log.error(str(exc))
            passed = False
        results[plan["name"]] = "PASS" if passed else "FAIL"

    log.section("RESULTS SUMMARY")
    for name, result in results.items():
        log.detail(f"[{result}] {name}")
    log.artifact(ARTIFACTS)

    return 0 if all(result == "PASS" for result in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
