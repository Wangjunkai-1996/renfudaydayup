#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(git rev-parse --show-toplevel)}"
DEPLOY_SCRIPT="${DEPLOY_SCRIPT:-${REPO_ROOT}/scripts/deploy_server.sh}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-master}"
DEPLOY_REMOTE="${DEPLOY_REMOTE:-origin}"
HOOK_LOG="${HOOK_LOG:-/tmp/renfu-pre-push.log}"
LATEST_TARGET_FILE="${LATEST_TARGET_FILE:-/tmp/renfu-pre-push.state.d/latest_target}"
DEPLOY_DEBOUNCE_SEC="${DEPLOY_DEBOUNCE_SEC:-8}"
EXPECTED_SHA="${EXPECTED_SHA:-}"

target_ref="refs/heads/${DEPLOY_BRANCH}"

cd "${REPO_ROOT}"

log() {
  echo "[$(date '+%F %T')] $*" >> "${HOOK_LOG}"
}

read_latest_sha() {
  if [[ ! -f "${LATEST_TARGET_FILE}" ]]; then
    return 1
  fi
  sed -n 's/^sha=//p' "${LATEST_TARGET_FILE}" | head -n 1
}

is_latest_target() {
  local sha="$1"
  local current_sha
  current_sha="$(read_latest_sha || true)"
  [[ -n "${current_sha}" && "${current_sha}" == "${sha}" ]]
}

latest_sha() {
  read_latest_sha || true
}

if [[ -z "${EXPECTED_SHA}" ]]; then
  log "skip deploy: missing EXPECTED_SHA"
  exit 0
fi

log "detected push to ${DEPLOY_REMOTE}/${DEPLOY_BRANCH}, latest target ${EXPECTED_SHA}"

synced=0
for _ in $(seq 1 45); do
  if ! is_latest_target "${EXPECTED_SHA}"; then
    log "skip deploy wait: superseded by newer target $(latest_sha)"
    exit 0
  fi

  remote_line="$(git ls-remote "${DEPLOY_REMOTE}" "${target_ref}" || true)"
  remote_sha="${remote_line%%[[:space:]]*}"
  if [[ "${remote_sha}" == "${EXPECTED_SHA}" ]]; then
    synced=1
    break
  fi
  sleep 1
done

if [[ "${synced}" -ne 1 ]]; then
  log "skip deploy: remote ${target_ref} did not reach ${EXPECTED_SHA}"
  exit 0
fi

if [[ "${DEPLOY_DEBOUNCE_SEC}" =~ ^[0-9]+$ ]] && (( DEPLOY_DEBOUNCE_SEC > 0 )); then
  sleep "${DEPLOY_DEBOUNCE_SEC}"
fi

if ! is_latest_target "${EXPECTED_SHA}"; then
  log "skip deploy: superseded by newer target $(latest_sha)"
  exit 0
fi

log "running deploy script ${DEPLOY_SCRIPT} for ${EXPECTED_SHA}"
if DEPLOY_COMMIT_SHA="${EXPECTED_SHA}" DEPLOY_TARGET_FILE="${LATEST_TARGET_FILE}" "${DEPLOY_SCRIPT}" >> "${HOOK_LOG}" 2>&1; then
  log "deploy finished for ${EXPECTED_SHA}"
else
  log "deploy failed for ${EXPECTED_SHA}"
fi
