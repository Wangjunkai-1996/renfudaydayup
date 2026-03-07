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
REMOTE_CHECK_TIMEOUT_SEC="${REMOTE_CHECK_TIMEOUT_SEC:-5}"
REMOTE_CHECK_MAX_ATTEMPTS="${REMOTE_CHECK_MAX_ATTEMPTS:-45}"
REMOTE_CHECK_INTERVAL_SEC="${REMOTE_CHECK_INTERVAL_SEC:-1}"

target_ref="refs/heads/${DEPLOY_BRANCH}"
REMOTE_CHECK_ERROR=""

cd "${REPO_ROOT}"

log() {
  echo "[$(date '+%F %T')] $*" >> "${HOOK_LOG}"
}

sanitize_log_text() {
  tr '\n' ' ' | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//'
}

resolve_remote_url() {
  git remote get-url --push "${DEPLOY_REMOTE}" 2>/dev/null || git remote get-url "${DEPLOY_REMOTE}" 2>/dev/null || true
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

fetch_remote_sha() {
  local remote_url remote_line remote_sha err_file ssh_cmd

  remote_url="$(resolve_remote_url)"
  if [[ -z "${remote_url}" ]]; then
    REMOTE_CHECK_ERROR="unable to resolve remote url for ${DEPLOY_REMOTE}"
    return 1
  fi

  err_file="$(mktemp /tmp/renfu-ls-remote.XXXXXX)"
  ssh_cmd="${GIT_SSH_COMMAND:-ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=${REMOTE_CHECK_TIMEOUT_SEC} -o ConnectionAttempts=1}"

  if remote_line="$(GIT_SSH_COMMAND="${ssh_cmd}" git ls-remote "${remote_url}" "${target_ref}" 2>"${err_file}")"; then
    rm -f "${err_file}"
    remote_sha="${remote_line%%[[:space:]]*}"
    if [[ -z "${remote_sha}" ]]; then
      REMOTE_CHECK_ERROR="remote ${remote_url} returned empty sha for ${target_ref}"
      return 1
    fi
    printf '%s\n' "${remote_sha}"
    return 0
  fi

  REMOTE_CHECK_ERROR="$(sanitize_log_text < "${err_file}")"
  rm -f "${err_file}"
  if [[ -z "${REMOTE_CHECK_ERROR}" ]]; then
    REMOTE_CHECK_ERROR="unknown ls-remote failure for ${remote_url}"
  fi
  return 1
}

if [[ -z "${EXPECTED_SHA}" ]]; then
  log "skip deploy: missing EXPECTED_SHA"
  exit 0
fi

remote_display="$(resolve_remote_url)"
log "detected push to ${DEPLOY_REMOTE}/${DEPLOY_BRANCH}, latest target ${EXPECTED_SHA}, remote ${remote_display:-unknown}"

synced=0
for attempt in $(seq 1 "${REMOTE_CHECK_MAX_ATTEMPTS}"); do
  if ! is_latest_target "${EXPECTED_SHA}"; then
    log "skip deploy wait: superseded by newer target $(latest_sha)"
    exit 0
  fi

  if remote_sha="$(fetch_remote_sha)"; then
    if [[ "${remote_sha}" == "${EXPECTED_SHA}" ]]; then
      synced=1
      break
    fi
    if (( attempt == 1 || attempt % 10 == 0 )); then
      log "waiting for remote ${target_ref}: saw ${remote_sha}, need ${EXPECTED_SHA}"
    fi
  elif (( attempt == 1 || attempt % 5 == 0 )); then
    log "waiting for remote ${target_ref}: ${REMOTE_CHECK_ERROR}"
  fi

  sleep "${REMOTE_CHECK_INTERVAL_SEC}"
done

if [[ "${synced}" -ne 1 ]]; then
  if [[ -n "${REMOTE_CHECK_ERROR}" ]]; then
    log "skip deploy: remote ${target_ref} did not reach ${EXPECTED_SHA}; last error: ${REMOTE_CHECK_ERROR}"
  else
    log "skip deploy: remote ${target_ref} did not reach ${EXPECTED_SHA}"
  fi
  exit 0
fi

log "remote ${target_ref} reached ${EXPECTED_SHA}"

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
