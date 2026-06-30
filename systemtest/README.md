# MATLAB Bamboo Plugin System Tests

This directory contains self-contained system tests for the MATLAB Bamboo
plugin. The workflow mirrors the MATLAB TeamCity plugin system tests: start a
local CI server, configure build definitions through automation, run the MATLAB
plugin tasks, and validate the results.

## Workflow

1. Tear down any Bamboo process left from a previous run.
2. Move the generated `target` directory aside to avoid Windows/OneDrive file
   locks during AMPS startup.
3. Build the plugin with AMPS/Maven.
4. Start a local Bamboo AMPS dev instance.
5. Probe Bamboo readiness and setup/licensing state.
6. Configure the default Bamboo agent with the MATLAB capability.
7. Publish three Bamboo Specs plans:
   - `MSYS-CMD`: Run MATLAB Command
   - `MSYS-BLD`: Run MATLAB Build
   - `MSYS-TST`: Run MATLAB Tests
8. Trigger each plan through Bamboo REST.
9. Validate command/build log output and JUnit XML from the test task.
10. Leave Bamboo running so the UI can be inspected at
    `http://localhost:6990/bamboo`.

Each new run starts with teardown, so the previous Bamboo server is closed
before a fresh server starts. Logs, REST payloads, and downloaded artifacts are
collected under `systemtest/artifacts`.

For local testing without the Atlassian SDK, Maven can use the project-local
settings file:

```powershell
& "..\.tools\maven\bin\mvn.cmd" -s systemtest\maven-settings.xml -B package -DskipTests
```

To run the full system-test workflow:

```powershell
python -u systemtest\run_system_tests.py
```

After the workflow completes, Bamboo remains available for inspection:

```text
http://localhost:6990/bamboo
```

Use `admin` / `admin` to sign in. The next `run_system_tests.py` execution will
close this server as its first step.

## Environment Variables

| Name | Default | Purpose |
| --- | --- | --- |
| `BAMBOO_URL` | `http://localhost:6990/bamboo` | Bamboo base URL. |
| `BAMBOO_USERNAME` | `admin` | Admin username for API-ready checks. |
| `BAMBOO_PASSWORD` | `admin` | Admin password for API-ready checks. |
| `BAMBOO_LICENSE` | empty | Optional Bamboo license for future setup automation. |
| `MATLAB_PATH` | auto-detected | MATLAB root used by future plan/capability setup. |
| `MATLAB_BAMBOO_CAPABILITY` | `MATLAB R2026a` | Bamboo executable label used in plugin task configs. |
| `MAVEN_CMD` | auto-detected | Maven command used when Atlassian SDK is unavailable. |

## Current Status

The full workflow has passed locally in AMPS dev mode. Bamboo starts with a
dev/evaluation license, `admin/admin` REST access works, the default local
agent starts, the MATLAB Bamboo plugin loads, and all three MATLAB plans pass.

The local run is intentionally verbose. It prints AMPS startup milestones,
Bamboo HTTP polling, REST/API checks, Specs publishing progress, per-plan build
state, log validation, JUnit artifact validation, and the final Bamboo URL.
