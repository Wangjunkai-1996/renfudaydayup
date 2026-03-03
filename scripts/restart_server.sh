#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PORT="${PORT:-8080}"
LOG_PATH="${LOG_PATH:-data/server.log}"
PID_PATH="${PID_PATH:-data/server.pid}"

mkdir -p data

OLD_PIDS="$(lsof -tiTCP:${PORT} -sTCP:LISTEN || true)"
if [[ -n "${OLD_PIDS}" ]]; then
  echo "Stopping existing process on port ${PORT}: ${OLD_PIDS}"
  kill ${OLD_PIDS} || true
  sleep 1
  STILL_PIDS="$(lsof -tiTCP:${PORT} -sTCP:LISTEN || true)"
  if [[ -n "${STILL_PIDS}" ]]; then
    echo "Force killing process on port ${PORT}: ${STILL_PIDS}"
    kill -9 ${STILL_PIDS} || true
  fi
fi

nohup python3 app.py > "${LOG_PATH}" 2>&1 &
NEW_PID=$!
echo "${NEW_PID}" > "${PID_PATH}"

READY=0
for _ in {1..20}; do
  if lsof -nP -iTCP:${PORT} -sTCP:LISTEN >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 0.5
done

if [[ "${READY}" -eq 1 ]]; then
  echo "Server restarted on port ${PORT}, pid=${NEW_PID}"
  echo "Log: ${LOG_PATH}"
else
  echo "Server failed to start, check log: ${LOG_PATH}"
  if [[ -f "${LOG_PATH}" ]]; then
    tail -n 40 "${LOG_PATH}" || true
  fi
  exit 1
fi
