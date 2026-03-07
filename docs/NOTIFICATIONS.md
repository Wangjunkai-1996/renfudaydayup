# Notifications

This project can push key events to WeChat via Server酱 (ServerChan Turbo).

## Supported Events

- BUY / SELL signal accepted
- Risk pause triggered
- Push-triggered deploy failed
- Push-triggered deploy succeeded when `DEPLOY_SERVERCHAN_SUCCESS=1`

## Server Runtime Setup

Add these environment variables to `/etc/renfu.env` on the server:

```bash
SERVERCHAN_SENDKEY=YOUR_SENDKEY
SERVERCHAN_ENABLED=1
SERVERCHAN_TITLE_PREFIX=Renfu
SERVERCHAN_NOTIFY_OPEN=1
SERVERCHAN_NOTIFY_RISK=1
```

Then restart the service:

```bash
systemctl restart renfu
```

## Local Push Deploy Setup

The Git hook deploy script runs on your local machine, so deploy notifications need the key in your local shell environment:

```bash
export SERVERCHAN_SENDKEY=YOUR_SENDKEY
export DEPLOY_SERVERCHAN_SUCCESS=0
```

For a persistent local setup, create `${HOME}/.renfu.deploy.env`:

```bash
SERVERCHAN_SENDKEY=YOUR_SENDKEY
DEPLOY_SERVERCHAN_ENABLED=1
DEPLOY_SERVERCHAN_SUCCESS=0
```

If you only want failure notifications, keep `DEPLOY_SERVERCHAN_SUCCESS=0`.

## Test Notification API

After the server key is configured, you can trigger a test message with:

```bash
curl -X POST http://127.0.0.1:8080/api/notify/test \
  -H 'Content-Type: application/json' \
  -d '{"title":"测试通知","body":"### 测试\n- 这是一条测试消息"}'
```

If `API_AUTH_TOKEN` is enabled, also add `-H 'X-API-Token: ...'`.
