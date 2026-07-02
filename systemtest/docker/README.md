# Docker Bamboo System Test

This folder runs the existing Bamboo system-test workflow inside a Linux
container. It is designed for clean CI jobs where the container and workspace
start fresh for each run.

## What This Tests

The container starts Bamboo with Maven/AMPS, configures the MATLAB Bamboo agent
capability, publishes the Bamboo Specs plans, runs the three MATLAB plans, and
collects artifacts under `systemtest/artifacts`.

The repository is bind-mounted into the container, so local source changes are
tested directly.

The Docker workflow starts directly because a Linux CI job should not reuse a
previous Bamboo server or generated workspace. Container exit owns process
cleanup after the test command completes.

The default container command runs `docker/run-systemtest.sh`, which verifies
that `MATLAB_PATH/bin/matlab` exists and can start in batch mode before starting
Bamboo. In the TeamCity-style image, `MATLAB_PATH` points at a small adapter
root whose `bin/matlab` delegates `-batch` and `-r` calls to `matlab-batch`.

## MATLAB Requirement

The Linux container must be able to execute MATLAB from `MATLAB_PATH`.
It also needs a MATLAB license, just like a TeamCity agent container.

A Windows MATLAB installation cannot be executed inside this Linux container.
Use one of these options:

- Build the Docker image with Linux MATLAB installed using
  `compose.with-matlab.yml`. This matches the TeamCity-style agent-container
  approach.
- Mount a Linux MATLAB installation with `compose.matlab-volume.yml`.
- Use the existing Linux runner workflow when MATLAB is installed on the runner.

## Run With Docker Desktop

From the repository root:

```powershell
Copy-Item systemtest\docker\.env.example systemtest\docker\.env
docker compose --env-file systemtest\docker\.env -f systemtest\docker\compose.yml build
docker compose --env-file systemtest\docker\.env -f systemtest\docker\compose.yml run --rm --service-ports bamboo-systemtest
```

## TeamCity-Style Image With MATLAB Installed

This builds an image that installs Linux MATLAB with MathWorks Package Manager
during `docker build`, installs `matlab-batch`, and exposes a MATLAB-root-shaped
adapter for the Bamboo capability. Edit `systemtest\docker\.env` first if you
need a different release or product list.

```powershell
docker compose --env-file systemtest\docker\.env `
  -f systemtest\docker\compose.yml `
  -f systemtest\docker\compose.with-matlab.yml `
  build

docker compose --env-file systemtest\docker\.env `
  -f systemtest\docker\compose.yml `
  -f systemtest\docker\compose.with-matlab.yml `
  run --rm --service-ports bamboo-systemtest
```

Relevant `.env` values:

```text
MATLAB_RELEASE=R2026a
MATLAB_INSTALL_ROOT=/opt/matlab
MATLAB_BATCH_ADAPTER_ROOT=/opt/matlab-batch-adapter
MATLAB_PRODUCTS=MATLAB
MATLAB_PATH=/opt/matlab-batch-adapter
REAL_MATLAB_ROOT=/opt/matlab/R2026a
MLM_LICENSE_TOKEN=user@email.com|profile|encodedToken
```

For a TeamCity-style batch token, set `MLM_LICENSE_TOKEN` in
`systemtest\docker\.env` or pass it as an environment variable when invoking
Docker Compose. Do not commit real token values.

For a license server, set `MLM_LICENSE_FILE` in `systemtest\docker\.env` and
point `MATLAB_PATH` at the real MATLAB root instead of the adapter:

```text
MATLAB_PATH=/opt/matlab/R2026a
MLM_LICENSE_FILE=27000@host.docker.internal
```

When the license server runs on the Windows host, `host.docker.internal` is the
hostname visible from Docker Desktop Linux containers.

For a license file, set `MATLAB_LICENSE_FILE_HOST` in `systemtest\docker\.env`
and add the license-file override:

```powershell
docker compose --env-file systemtest\docker\.env `
  -f systemtest\docker\compose.yml `
  -f systemtest\docker\compose.with-matlab.yml `
  -f systemtest\docker\compose.license-file.yml `
  run --rm --service-ports bamboo-systemtest
```

To mount a Linux MATLAB installation:

```powershell
# Edit systemtest\docker\.env first:
# MATLAB_HOST_ROOT=/absolute/path/to/linux/MATLAB/R2026a
# MATLAB_PATH=/opt/matlab/R2026a

docker compose --env-file systemtest\docker\.env `
  -f systemtest\docker\compose.yml `
  -f systemtest\docker\compose.matlab-volume.yml `
  run --rm --service-ports bamboo-systemtest
```

## Artifacts

The same artifact folder is used:

```text
systemtest/artifacts
```

Important files:

- `bamboo-run.log`: full Maven/AMPS Bamboo startup log
- `specs-publish.log`: Maven output from Bamboo Specs publishing
- `log-MSYS-*.txt`: Bamboo plan logs
- `junit.xml`: MATLAB test results

## Notes

- When the test command exits, Docker stops the container and Bamboo exits with
  it.
- Maven dependencies are cached in a Docker volume named `maven-cache`.
- Plugin build output is written under the checked-out workspace `target`
  directory. In CI this workspace is expected to be fresh for each job.
- The MATLAB-installed image can be large and slow to build. Reuse it for local
  iterations once it is built.
