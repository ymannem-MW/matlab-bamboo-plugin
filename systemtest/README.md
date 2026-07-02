# MATLAB Bamboo Plugin System Tests

This directory contains self-contained system tests for the MATLAB Bamboo
plugin. The workflow mirrors the MATLAB TeamCity plugin system tests: start a
Bamboo test server, configure build definitions through automation, run the MATLAB
plugin tasks, and validate the results.

## Workflow

1. Build the plugin with AMPS/Maven.
2. Start a Bamboo AMPS dev instance.
3. Probe Bamboo readiness and setup/licensing state.
4. Configure the default Bamboo agent with the MATLAB capability.
5. Publish three Bamboo Specs plans:
   - `MSYS-CMD`: Run MATLAB Command
   - `MSYS-BLD`: Run MATLAB Build
   - `MSYS-TST`: Run MATLAB Tests
6. Trigger each plan through Bamboo REST.
7. Validate command/build log output and JUnit XML from the test task.
8. Exit with the system-test result. The CI runner or container lifecycle
   cleans up Bamboo after the job.

The workflow assumes a fresh CI runner/workspace. Logs, REST payloads, and
downloaded artifacts are collected under `systemtest/artifacts`.

For direct Maven commands, use the system-test settings file:

```powershell
& "..\.tools\maven\bin\mvn.cmd" -s systemtest\maven-settings.xml -B package -DskipTests
```

To run the full system-test workflow in CI:

```powershell
python -u systemtest\run_system_tests.py
```

An optional Linux Docker harness is available under `systemtest/docker`. It runs
the same `run_system_tests.py` workflow inside a container, but it still needs a
Linux MATLAB installation available at `MATLAB_PATH`.

When debugging an active run with the Bamboo port exposed, Bamboo is available
at:

```text
http://localhost:6990/bamboo
```

Use `admin` / `admin` to sign in while the job is still running.

To inspect the agent capability in Bamboo:

1. Open `http://localhost:6990/bamboo` and sign in with `admin` / `admin`.
2. Open the administration menu.
3. Go to `Overview` > `Agents`.
4. Open `Default Agent`.
5. Open `Capabilities` and look for `system.builder.matlab.MATLAB R2026a`.

## Environment Variables

| Name | Default | Purpose |
| --- | --- | --- |
| `BAMBOO_URL` | `http://localhost:6990/bamboo` | Bamboo base URL. |
| `BAMBOO_USERNAME` | `admin` | Admin username for API-ready checks. |
| `BAMBOO_PASSWORD` | `admin` | Admin password for API-ready checks. |
| `BAMBOO_LICENSE` | empty | Optional Bamboo license for future setup automation. |
| `MATLAB_PATH` | auto-detected | MATLAB root used by future plan/capability setup. |
| `MATLAB_BAMBOO_CAPABILITY` | `MATLAB R2026a` | Bamboo executable label used in plugin task configs. |
| `MAVEN_CMD` | auto-detected | Maven command used to run AMPS goals. |

## Logging

The run prints AMPS startup milestones, Bamboo HTTP polling, REST/API checks,
Specs publishing progress, per-plan build state, log validation, JUnit artifact
validation, and the final Bamboo process state.
