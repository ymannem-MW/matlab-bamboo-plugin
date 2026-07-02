#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "-batch" || "${1:-}" == "-r" ]]; then
  mode="$1"
  shift
  if [[ $# -lt 1 ]]; then
    echo "Usage: matlab ${mode} <statement>" >&2
    exit 2
  fi
  statement="$1"
  shift
  export PATH="${REAL_MATLAB_ROOT:-/opt/matlab/R2026a}/bin:${PATH}"
  exec matlab-batch "$@" "${statement}"
fi

exec "${REAL_MATLAB_ROOT:-/opt/matlab/R2026a}/bin/matlab" "$@"
