#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DJANGO_DIR="$SCRIPT_DIR/yolo_system"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$DJANGO_DIR"

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM

  if [[ -n "${PLC_PID:-}" ]] && kill -0 "$PLC_PID" 2>/dev/null; then
    kill "$PLC_PID" 2>/dev/null || true
  fi

  if [[ -n "${DJANGO_PID:-}" ]] && kill -0 "$DJANGO_PID" 2>/dev/null; then
    kill "$DJANGO_PID" 2>/dev/null || true
  fi

  wait "${PLC_PID:-}" 2>/dev/null || true
  wait "${DJANGO_PID:-}" 2>/dev/null || true
  exit "$exit_code"
}

trap cleanup EXIT INT TERM

echo "Starting Django server..."
"$PYTHON_BIN" manage.py runserver &
DJANGO_PID=$!

echo "Starting PLC monitor..."
"$PYTHON_BIN" manage.py run_plc_monitor &
PLC_PID=$!

echo "Django server PID: $DJANGO_PID"
echo "PLC monitor PID: $PLC_PID"
echo "Press Ctrl+C to stop both processes."

wait -n "$DJANGO_PID" "$PLC_PID"