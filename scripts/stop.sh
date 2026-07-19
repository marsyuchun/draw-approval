#!/bin/zsh
set -euo pipefail

ROOT_DIR="${0:A:h:h}"
RUNTIME_DIR="$ROOT_DIR/.runtime"

stop_service() {
  local name="$1"
  local pid_file="$RUNTIME_DIR/$name.pid"
  if [[ ! -f "$pid_file" ]]; then
    echo "$name 服务未运行。"
    return
  fi

  local pid="$(<"$pid_file")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    for _ in {1..10}; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 1
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid"
    fi
    echo "$name 服务已停止。"
  else
    echo "$name 服务进程不存在，已清理状态文件。"
  fi
  rm -f "$pid_file"
}

stop_service frontend
stop_service backend
