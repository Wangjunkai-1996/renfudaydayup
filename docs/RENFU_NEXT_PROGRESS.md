# Renfu Next 当前进度

更新日期：2026-03-07

## 当前已完成
- 新后端已可运行，入口：`backend/app/main.py`
- 新前端已可运行，入口：`frontend/src/main.ts`
- 旧 Flask 可挂载到 `/legacy`
- 新 API 已形成统一前缀 `/api/v1`
- 新 WebSocket 已形成统一入口 `/ws/v1/stream`
- 用户登录、管理员建用户、用户隔离测试已通过
- 前端单测与生产构建已通过
- 迁移脚本、worker stub、说明文档、自动任务目录均已落盘

## 当前仍是“基础完成，业务迁移未完成”
以下部分还没有完全替换成旧系统真实逻辑：
- worker 中的实时行情抓取与真实策略执行
- reports / diagnostics 中普通用户接口仍有一部分是过渡实现，但 `legacy_admin` 已桥接旧系统真实逻辑
- tuning 仍是新栈独立 JSON 配置逻辑，还未对齐旧全局调优链路
- 前端还缺少实时状态同步、细化交互和部分业务表单

## 已验证结果
- `python3 -m compileall backend/app backend/tests scripts/migrate_legacy_to_postgres.py`
- `backend/.venv/bin/pytest backend/tests -q` 通过
- `cd frontend && npm run test:run` 通过
- `cd frontend && npm run build` 通过

## 已知问题
- `/legacy` 挂载使用的是 Starlette 的 WSGI 兼容层，测试里有弃用警告，但目前功能可用。
- 前端首包目前偏大，后续要做路由分包和图表模块拆分。
- 目前后端正式目标是 PostgreSQL，但本地验证仍兼容 SQLite。

## 推荐下一步
- 优先桥接旧系统真实报表与诊断逻辑到新 API。
- 再替换 worker stub，接入旧行情 / 策略引擎。
- 最后补生产部署、前端实时流和页面细化。
