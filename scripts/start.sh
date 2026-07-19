#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
RUNTIME_DIR="$ROOT_DIR/.runtime"
BACKEND_PID_FILE="$RUNTIME_DIR/backend.pid"
FRONTEND_PID_FILE="$RUNTIME_DIR/frontend.pid"
BACKEND_LOG="$RUNTIME_DIR/backend.log"
FRONTEND_LOG="$RUNTIME_DIR/frontend.log"
PYTHON_BIN="$ROOT_DIR/backend/.venv/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

is_running() {
  [[ -f "$1" ]] && kill -0 "$(<"$1")" 2>/dev/null
}

mkdir -p "$RUNTIME_DIR"

if is_running "$BACKEND_PID_FILE" || is_running "$FRONTEND_PID_FILE"; then
  echo "服务已在运行。前端：http://127.0.0.1:5173  后端：http://127.0.0.1:8000"
  exit 0
fi

if [[ ! -x "$ROOT_DIR/frontend/node_modules/.bin/vite" ]]; then
  echo "前端依赖未安装。请先双击或执行 scripts/deploy.sh。"
  exit 1
fi

if ! "$PYTHON_BIN" -c 'import ezdxf, fitz' 2>/dev/null; then
  echo "后端依赖未安装。请先双击或执行 scripts/deploy.sh。"
  exit 1
fi

rm -f "$BACKEND_PID_FILE" "$FRONTEND_PID_FILE"
(
  cd "$ROOT_DIR/backend"
  nohup "$PYTHON_BIN" run.py >"$BACKEND_LOG" 2>&1 &
  echo $! >"$BACKEND_PID_FILE"
)

for _ in {1..30}; do
  if curl --noproxy '*' -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! is_running "$BACKEND_PID_FILE" || ! curl --noproxy '*' -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  echo "后端启动失败，请查看 $BACKEND_LOG"
  rm -f "$BACKEND_PID_FILE"
  exit 1
fi

(
  cd "$ROOT_DIR/frontend"
  nohup npm run dev -- --host 127.0.0.1 --port 5173 --strictPort >"$FRONTEND_LOG" 2>&1 &
  echo $! >"$FRONTEND_PID_FILE"
)

sleep 2
if ! is_running "$FRONTEND_PID_FILE"; then
  echo "前端启动失败，请查看 $FRONTEND_LOG"
  "$ROOT_DIR/scripts/stop.sh"
  exit 1
fi

echo "启动完成"
echo "前端：http://127.0.0.1:5173"
echo "后端：http://127.0.0.1:8000"
