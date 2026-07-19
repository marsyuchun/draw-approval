#!/bin/zsh
set -euo pipefail

ROOT_DIR="${0:A:h:h}"
"$ROOT_DIR/scripts/stop.sh"
"$ROOT_DIR/scripts/start.sh"
