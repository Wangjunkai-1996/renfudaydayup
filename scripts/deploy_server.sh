#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SERVER_HOST="${SERVER_HOST:-renfu-prod}"
SERVER_USER="${SERVER_USER:-root}"
SERVER_APP_DIR="${SERVER_APP_DIR:-/www/wwwroot/renfu}"
PYPI_INDEX="${PYPI_INDEX:-https://mirrors.aliyun.com/pypi/simple}"
RSYNC_DELETE="${RSYNC_DELETE:-0}"

if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync 未安装，请先安装 rsync。"
  exit 1
fi

if ! command -v ssh >/dev/null 2>&1; then
  echo "ssh 未安装，请先安装 openssh 客户端。"
  exit 1
fi

echo "==> Sync code to ${SERVER_USER}@${SERVER_HOST}:${SERVER_APP_DIR}"
RSYNC_FLAGS=(-avz)
if [ "${RSYNC_DELETE}" = "1" ]; then
  RSYNC_FLAGS+=(--delete)
fi

rsync "${RSYNC_FLAGS[@]}" \
  --exclude ".git" \
  --exclude ".venv" \
  --exclude "data/" \
  -e "ssh -o StrictHostKeyChecking=accept-new" \
  "${ROOT_DIR}/" "${SERVER_USER}@${SERVER_HOST}:${SERVER_APP_DIR}/"

echo "==> Install deps, restart service, and check health"
ssh -o StrictHostKeyChecking=accept-new "${SERVER_USER}@${SERVER_HOST}" \
  "set -euo pipefail; cd '${SERVER_APP_DIR}'; if [ ! -x ./.venv/bin/pip ]; then (python3 -m venv .venv || python -m venv .venv); fi; ./.venv/bin/pip install -U pip; ./.venv/bin/pip install -r requirements.txt -i '${PYPI_INDEX}'; systemctl restart renfu; systemctl is-active renfu; ok=0; for i in \$(seq 1 30); do if curl -fsS http://127.0.0.1:8080/api/health >/dev/null 2>&1; then ok=1; break; fi; sleep 1; done; if [ \"\$ok\" -ne 1 ]; then systemctl status renfu --no-pager -l; journalctl -u renfu -n 80 --no-pager; exit 1; fi; curl -fsS http://127.0.0.1:8080/api/health"

echo "==> Deploy finished"
