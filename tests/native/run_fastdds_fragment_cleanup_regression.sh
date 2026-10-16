#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
PREFIX="${MARSDOG_FASTDDS_PREFIX:-${HOME}/.local/opt/marsdog-fastdds-2.6.12}"
ROS_PREFIX="${ROS_PREFIX:-/opt/ros/humble}"
SOURCE="${PROJECT_DIR}/tests/native/fastdds_fragment_cleanup_regression.cpp"

find_library_dir() {
  local root="$1"
  local candidate
  for candidate in "${root}/lib" "${root}/lib64" "${root}/lib/aarch64-linux-gnu"; do
    if [[ -f "${candidate}/libfastrtps.so.2.6" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done
  return 1
}

if ! LIB_DIR="$(find_library_dir "${PREFIX}")"; then
  echo "Patched Fast DDS 2.6.12 was not found under ${PREFIX}. Run scripts/build_fastdds.sh first." >&2
  exit 2
fi

TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/marsdog-fastdds-regression.XXXXXX")"
trap 'rm -rf "${TEMP_DIR}"' EXIT
CXX="${CXX:-c++}"
"${CXX}" -std=c++17 -O0 \
  -I"${ROS_PREFIX}/include/fastrtps" \
  -I"${ROS_PREFIX}/include/fastcdr" \
  "${SOURCE}" \
  -L"${LIB_DIR}" -L"${ROS_PREFIX}/lib" \
  -Wl,-rpath,"${LIB_DIR}" -Wl,-rpath,"${ROS_PREFIX}/lib" \
  -lfastrtps -lfastcdr -lpthread \
  -o "${TEMP_DIR}/fastdds_fragment_cleanup_regression"

LD_LIBRARY_PATH="${LIB_DIR}:${ROS_PREFIX}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}" \
  "${TEMP_DIR}/fastdds_fragment_cleanup_regression"
