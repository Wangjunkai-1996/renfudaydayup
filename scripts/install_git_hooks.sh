#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

HOOKS_PATH=".githooks"
PRE_PUSH_HOOK="${HOOKS_PATH}/pre-push"

if [[ ! -d .git ]]; then
  echo "未检测到 .git 目录，请在仓库根目录运行。"
  exit 1
fi

if [[ ! -f "${PRE_PUSH_HOOK}" ]]; then
  echo "缺少 hook 文件: ${PRE_PUSH_HOOK}"
  exit 1
fi

chmod +x "${PRE_PUSH_HOOK}"
git config core.hooksPath "${HOOKS_PATH}"

echo "Git hooks 已切换到 ${HOOKS_PATH}"
echo "当前 pre-push hook: ${REPO_ROOT}/${PRE_PUSH_HOOK}"
echo "部署日志: /tmp/renfu-pre-push.log"
