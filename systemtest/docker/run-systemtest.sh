#!/usr/bin/env bash
set -euo pipefail

matlab_root="${MATLAB_PATH:-/opt/matlab/R2026a}"
matlab_executable="${matlab_root}/bin/matlab"

echo "Docker Bamboo system test"
echo "MATLAB_PATH=${matlab_root}"

if [[ ! -x "${matlab_executable}" ]]; then
  cat >&2 <<EOF
ERROR: MATLAB is not executable inside the Linux container.

Expected: ${matlab_executable}

Mount a Linux MATLAB installation with docker/compose.matlab-volume.yml, or use
a Docker image that already contains Linux MATLAB. A Windows MATLAB installation
cannot run inside this Linux container.
EOF
  exit 2
fi

echo "Checking MATLAB batch startup..."
"${matlab_executable}" -batch "disp('MATLAB Docker smoke passed')"

exec python3 -u run_system_tests.py
