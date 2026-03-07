# Deployment Workflow

## Auto Deploy Trigger

- Git push hook lives in `.githooks/pre-push` and is versioned with the repository.
- The hook triggers only when pushing `origin/master` by default.
- Each matching push updates a local “latest target” state file, and only the newest target is deployed.
- After the remote branch reaches the pushed commit SHA, the hook waits briefly, then starts `scripts/run_deploy_after_push.sh` with `nohup` in the background.
- The background runner is detached from stdin, and remote SHA checks use non-interactive SSH with a short timeout so they do not hang on prompts.
- Hook logs are written to `/tmp/renfu-pre-push.log`.

## One-Time Setup

Run this once after cloning the repo:

```bash
./scripts/install_git_hooks.sh
```

That command sets `core.hooksPath` to `.githooks`, and ensures `.githooks/pre-push`, `scripts/run_deploy_after_push.sh`, and `scripts/deploy_server.sh` are executable.

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
- Can also push deploy success/failure to Server酱 when a SendKey is configured locally

## Useful Environment Variables

- `DEPLOY_REMOTE`: Git remote to watch, default `origin`
- `DEPLOY_BRANCH`: Git branch to watch, default `master`
- `HOOK_LOG`: Hook log path, default `/tmp/renfu-pre-push.log`
- `HOOK_STATE_DIR`: hook state directory, default `/tmp/renfu-pre-push.state.d`
- `LATEST_TARGET_FILE`: latest queued deploy target file, default `${HOOK_STATE_DIR}/latest_target`
- `DEPLOY_DEBOUNCE_SEC`: debounce window before deploy starts, default `8`
- `REMOTE_CHECK_TIMEOUT_SEC`: timeout per remote SHA check, default `5`
- `REMOTE_CHECK_MAX_ATTEMPTS`: max remote SHA polling attempts, default `45`
- `REMOTE_CHECK_INTERVAL_SEC`: wait between remote SHA polls, default `1`
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
- `SERVERCHAN_SENDKEY`: shared SendKey for deploy notifications if `DEPLOY_SERVERCHAN_SENDKEY` is not set
- `DEPLOY_SERVERCHAN_ENABLED`: set to `0` to disable Server酱 deploy notifications
- `DEPLOY_SERVERCHAN_SUCCESS`: set to `1` to notify deploy success as well as failures
- `DEPLOY_SERVERCHAN_SENDKEY`: explicit SendKey used by `scripts/deploy_server.sh`
- `DEPLOY_SERVERCHAN_API_BASE`: Server酱 API base, default `https://sctapi.ftqq.com`
- `DEPLOY_SERVERCHAN_TITLE`: title prefix for Server酱 deploy messages
- `LAST_DEPLOY_STATUS_FILE`: latest local deploy status file, default `/tmp/renfu-last-deploy.status`
