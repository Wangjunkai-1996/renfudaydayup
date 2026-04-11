#!/bin/zsh

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

export PATH="/opt/homebrew/bin:/usr/local/bin:/opt/homebrew/sbin:/usr/local/sbin:$PATH"

[[ -f "$HOME/.zprofile" ]] && source "$HOME/.zprofile"
[[ -f "$HOME/.zshrc" ]] && source "$HOME/.zshrc"

clear
echo "=================================================="
echo "Codex Intel Updater"
echo "Repo: $SCRIPT_DIR"
echo "=================================================="
echo

if ! command -v node >/dev/null 2>&1; then
  echo "Error: node command not found."
  echo "Please install Node.js first, then run again."
  echo
  if [[ -t 0 ]]; then
    read '?Press Enter to close...'
  fi
  exit 1
fi

node "$SCRIPT_DIR/update_codex_intel.js" "$@"
exit_code=$?

echo
if [[ $exit_code -eq 0 ]]; then
  echo "Update finished successfully."
else
  echo "Update failed with exit code $exit_code."
fi
echo

if [[ -t 0 ]]; then
  read '?Press Enter to close...'
fi

exit $exit_code
