#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}/frontend"

FRONTEND_PORT="${RENFU_NEXT_FRONTEND_PORT:-5173}"
API_PORT="${RENFU_NEXT_API_PORT:-9000}"
API_TARGET="${RENFU_NEXT_API_TARGET:-http://127.0.0.1:${API_PORT}}"

RENFU_NEXT_FRONTEND_PORT="${FRONTEND_PORT}" \
RENFU_NEXT_API_PORT="${API_PORT}" \
RENFU_NEXT_API_TARGET="${API_TARGET}" \
npm run dev -- --host 0.0.0.0 --port "${FRONTEND_PORT}"
