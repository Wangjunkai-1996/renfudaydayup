# Deployment Workflow

## Auto Deploy Trigger

- Git push hook lives in `.githooks/pre-push` and is versioned with the repository.
- The hook triggers only when pushing `origin/master` by default.
- Each matching push updates a local “latest target” state file, and only the newest target is deployed.
- After the remote branch reaches the pushed commit SHA, the hook waits briefly, then starts `scripts/run_deploy_after_push.sh` with `nohup`, which calls `scripts/deploy_server.sh` in the background.
- Hook logs are written to `/tmp/renfu-pre-push.log`.

## One-Time Setup

Run this once after cloning the repo:

```bash
./scripts/install_git_hooks.sh
```

That command sets `core.hooksPath` to `.githooks`, so Git uses the versioned hooks in this repository.

## Manual Deploy

You can deploy manually at any time:

```bash
./scripts/deploy_server.sh
```

## Deploy Script Behavior

- Syncs code to `${SERVER_USER}@${SERVER_HOST}:${SERVER_APP_DIR}` with `rsync`
- Excludes `.git/`, `.githooks/`, `.venv/`, `.pytest_cache/`, `__pycache__/`, and `data/`
- Collapses rapid consecutive pushes so only the latest queued commit is deployed
- Creates or reuses server-side `.venv`
- Installs dependencies from `requirements.txt`
- Restarts `renfu` via `systemctl`
- Checks `http://127.0.0.1:8080/api/health`
- Writes the latest local deploy result to `/tmp/renfu-last-deploy.status`
- Sends a local failure notification by default when deployment fails

## Useful Environment Variables

- `DEPLOY_REMOTE`: Git remote to watch, default `origin`
- `DEPLOY_BRANCH`: Git branch to watch, default `master`
- `HOOK_LOG`: Hook log path, default `/tmp/renfu-pre-push.log`
- `HOOK_STATE_DIR`: hook state directory, default `/tmp/renfu-pre-push.state.d`
- `LATEST_TARGET_FILE`: latest queued deploy target file, default `${HOOK_STATE_DIR}/latest_target`
- `DEPLOY_DEBOUNCE_SEC`: debounce window before deploy starts, default `8`
- `SERVER_HOST`: SSH host alias, default `renfu-prod`
- `SERVER_USER`: SSH user, default `root`
- `SERVER_APP_DIR`: remote app directory, default `/www/wwwroot/renfu`
- `PYPI_INDEX`: pip mirror URL
- `RSYNC_DELETE`: set to `1` to enable `rsync --delete`
- `DEPLOY_LOCK_DIR`: local deploy lock directory, default `/tmp/renfu-deploy.lock.d`
- `DEPLOY_LOCK_WAIT_SEC`: lock wait timeout in seconds, default `900`
- `DEPLOY_NOTIFY`: set to `0` to disable local notifications
- `DEPLOY_NOTIFY_SUCCESS`: set to `1` to also notify on success
- `DEPLOY_NOTIFY_TITLE`: notification title, default `Renfu Deploy`
- `LAST_DEPLOY_STATUS_FILE`: latest local deploy status file, default `/tmp/renfu-last-deploy.status`
