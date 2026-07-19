#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"

command -v node >/dev/null || { echo "未找到 Node.js，请先安装 Node.js 20 或更高版本。"; exit 1; }
command -v npm >/dev/null || { echo "未找到 npm。"; exit 1; }
command -v python3 >/dev/null || { echo "未找到 Python 3。"; exit 1; }

echo "安装前端依赖..."
(cd "$ROOT_DIR/frontend" && npm install)

echo "安装后端依赖..."
if [[ ! -x "$ROOT_DIR/backend/.venv/bin/python" ]]; then
  python3 -m venv "$ROOT_DIR/backend/.venv"
fi
"$ROOT_DIR/backend/.venv/bin/python" -m pip install --upgrade pip
"$ROOT_DIR/backend/.venv/bin/python" -m pip install -r "$ROOT_DIR/backend/requirements.txt"

"$ROOT_DIR/scripts/start.sh"
