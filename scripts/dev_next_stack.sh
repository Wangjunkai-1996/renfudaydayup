#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

printf 'Start backend with: %s\n' "${ROOT_DIR}/scripts/run_next_api.sh"
printf 'Start frontend with: %s\n' "cd ${ROOT_DIR}/frontend && npm install && npm run dev"
printf 'Legacy remains available from Flask under /legacy when backend starts.\n'
