#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SERVER_HOST="${SERVER_HOST:-renfu-prod}"
SERVER_USER="${SERVER_USER:-root}"
SERVER_APP_DIR="${SERVER_APP_DIR:-/www/wwwroot/renfu}"
PYPI_INDEX="${PYPI_INDEX:-https://mirrors.aliyun.com/pypi/simple}"
RSYNC_DELETE="${RSYNC_DELETE:-0}"
DEPLOY_LOCK_DIR="${DEPLOY_LOCK_DIR:-/tmp/renfu-deploy.lock.d}"
DEPLOY_LOCK_WAIT_SEC="${DEPLOY_LOCK_WAIT_SEC:-900}"
DEPLOY_COMMIT_SHA="${DEPLOY_COMMIT_SHA:-}"
DEPLOY_TARGET_FILE="${DEPLOY_TARGET_FILE:-}"
DEPLOY_NOTIFY="${DEPLOY_NOTIFY:-1}"
DEPLOY_NOTIFY_SUCCESS="${DEPLOY_NOTIFY_SUCCESS:-0}"
DEPLOY_NOTIFY_TITLE="${DEPLOY_NOTIFY_TITLE:-Renfu Deploy}"
LAST_DEPLOY_STATUS_FILE="${LAST_DEPLOY_STATUS_FILE:-/tmp/renfu-last-deploy.status}"

SUPERSEDED_BY=""
DEPLOY_OUTCOME="success"
DEPLOY_OUTCOME_MESSAGE="deploy finished"

escape_applescript_string() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

notify_local() {
  local subtitle="$1"
  local body="$2"

  if [[ "${DEPLOY_NOTIFY}" != "1" ]]; then
    return 0
  fi

  if command -v osascript >/dev/null 2>&1; then
    local title_escaped subtitle_escaped body_escaped
    title_escaped="$(escape_applescript_string "${DEPLOY_NOTIFY_TITLE}")"
    subtitle_escaped="$(escape_applescript_string "${subtitle}")"
    body_escaped="$(escape_applescript_string "${body}")"
    osascript >/dev/null 2>&1 <<OSA || true
display notification "${body_escaped}" with title "${title_escaped}" subtitle "${subtitle_escaped}"
OSA
    return 0
  fi

  if command -v notify-send >/dev/null 2>&1; then
    notify-send "${DEPLOY_NOTIFY_TITLE}: ${subtitle}" "${body}" >/dev/null 2>&1 || true
  fi
}

write_status() {
  local status="$1"
  local message="$2"
  {
    echo "status=${status}"
    echo "ts=$(date '+%F %T')"
    echo "commit=${DEPLOY_COMMIT_SHA}"
    echo "server=${SERVER_USER}@${SERVER_HOST}:${SERVER_APP_DIR}"
    echo "message=${message}"
  } > "${LAST_DEPLOY_STATUS_FILE}"
}

read_latest_target_sha() {
  if [[ -z "${DEPLOY_TARGET_FILE}" || ! -f "${DEPLOY_TARGET_FILE}" ]]; then
    return 1
  fi
  sed -n 's/^sha=//p' "${DEPLOY_TARGET_FILE}" | head -n 1
}

is_superseded() {
  local latest_sha
  latest_sha="$(read_latest_target_sha || true)"

  if [[ -n "${DEPLOY_COMMIT_SHA}" && -n "${latest_sha}" && "${latest_sha}" != "${DEPLOY_COMMIT_SHA}" ]]; then
    SUPERSEDED_BY="${latest_sha}"
    return 0
  fi

  return 1
}

acquire_lock() {
  local start_ts now_ts holder_pid
  start_ts="$(date +%s)"

  while ! mkdir "${DEPLOY_LOCK_DIR}" 2>/dev/null; do
    holder_pid="$(cat "${DEPLOY_LOCK_DIR}/pid" 2>/dev/null || true)"
    if [[ -n "${holder_pid}" ]] && ! kill -0 "${holder_pid}" 2>/dev/null; then
      rm -rf "${DEPLOY_LOCK_DIR}"
      continue
    fi

    now_ts="$(date +%s)"
    if (( now_ts - start_ts >= DEPLOY_LOCK_WAIT_SEC )); then
      echo "部署锁等待超时: ${DEPLOY_LOCK_DIR}"
      exit 1
    fi
    sleep 2
  done

  echo "$$" > "${DEPLOY_LOCK_DIR}/pid"
  trap 'rm -rf "${DEPLOY_LOCK_DIR}"' EXIT
}

main() {
  if is_superseded; then
    DEPLOY_OUTCOME="skipped"
    DEPLOY_OUTCOME_MESSAGE="superseded by ${SUPERSEDED_BY}"
    echo "==> Skip deploy for ${DEPLOY_COMMIT_SHA}, superseded by ${SUPERSEDED_BY}"
    return 0
  fi

  acquire_lock
  echo "==> Deploy lock acquired: ${DEPLOY_LOCK_DIR}"

  if is_superseded; then
    DEPLOY_OUTCOME="skipped"
    DEPLOY_OUTCOME_MESSAGE="superseded by ${SUPERSEDED_BY}"
    echo "==> Skip deploy for ${DEPLOY_COMMIT_SHA}, superseded by ${SUPERSEDED_BY}"
    return 0
  fi

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
    --exclude ".githooks" \
    --exclude ".venv" \
    --exclude ".pytest_cache" \
    --exclude "__pycache__" \
    --exclude "data/" \
    -e "ssh -o StrictHostKeyChecking=accept-new" \
    "${ROOT_DIR}/" "${SERVER_USER}@${SERVER_HOST}:${SERVER_APP_DIR}/"

  echo "==> Install deps, restart service, and check health"
  ssh -o StrictHostKeyChecking=accept-new "${SERVER_USER}@${SERVER_HOST}" \
    "set -euo pipefail; cd '${SERVER_APP_DIR}'; if [ ! -x ./.venv/bin/pip ]; then (python3 -m venv .venv || python -m venv .venv); fi; ./.venv/bin/pip install -U pip; ./.venv/bin/pip install -r requirements.txt -i '${PYPI_INDEX}'; systemctl restart renfu; systemctl is-active renfu; ok=0; for i in \$(seq 1 30); do if curl -fsS http://127.0.0.1:8080/api/health >/dev/null 2>&1; then ok=1; break; fi; sleep 1; done; if [ \"\$ok\" -ne 1 ]; then systemctl status renfu --no-pager -l; journalctl -u renfu -n 80 --no-pager; exit 1; fi; curl -fsS http://127.0.0.1:8080/api/health"

  if [[ -n "${DEPLOY_COMMIT_SHA}" ]]; then
    DEPLOY_OUTCOME_MESSAGE="deploy finished for ${DEPLOY_COMMIT_SHA}"
  else
    DEPLOY_OUTCOME_MESSAGE="deploy finished"
  fi
  echo "==> Deploy finished"
}

exit_code=0
if ! main; then
  exit_code=$?
  DEPLOY_OUTCOME="failed"
  if [[ -n "${DEPLOY_COMMIT_SHA}" ]]; then
    DEPLOY_OUTCOME_MESSAGE="deploy failed for ${DEPLOY_COMMIT_SHA} (exit=${exit_code})"
  else
    DEPLOY_OUTCOME_MESSAGE="deploy failed (exit=${exit_code})"
  fi
fi

write_status "${DEPLOY_OUTCOME}" "${DEPLOY_OUTCOME_MESSAGE}"

case "${DEPLOY_OUTCOME}" in
  success)
    if [[ "${DEPLOY_NOTIFY_SUCCESS}" == "1" ]]; then
      notify_local "Success" "${DEPLOY_OUTCOME_MESSAGE}"
    fi
    ;;
  failed)
    notify_local "Failed" "${DEPLOY_OUTCOME_MESSAGE}; log: /tmp/renfu-pre-push.log"
    ;;
  skipped)
    ;;
esac

exit "${exit_code}"
