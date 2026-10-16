#!/usr/bin/env bash
set -euo pipefail

DEMO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${DEMO_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

if [[ -z "${ROS_DISTRO:-}" ]]; then
  echo "ROS 2 is not sourced. Source /opt/ros/humble/setup.bash and this workspace's install/setup.bash first." >&2
  exit 2
fi

# Load the same patched Fast DDS overlay used by project launch files.
source "${PROJECT_DIR}/scripts/fastdds_env.sh"

exec uv run --project "${PROJECT_DIR}" python -m demo.vision_demo_node "$@"
