# Renfu Next 执行计划

## 目标
- 把当前 Flask 单体页面升级为前后端分离架构。
- 保留旧系统作为 `legacy` 对照入口。
- 新系统以多用户隔离、共享行情引擎、用户私有策略结果为核心。
- 支持后续持续扩展模块，而不再回到单页模板堆砌模式。

## 已锁定技术决策
- 前端：Vue 3 + Vite + TypeScript + Pinia + Vue Query + Tailwind + ECharts
- 后端：FastAPI + SQLAlchemy 2.x + Alembic
- 数据库：PostgreSQL 为正式目标，当前开发和测试兼容 SQLite
- 实时：REST + WebSocket
- 部署：同机部署，Nginx 托管前端并反代 API / WS
- 并行策略：新系统 `/app`，旧系统 `/legacy`

## 里程碑

### M1 基础架构
- [x] 建立 `backend/` 和 `frontend/` Monorepo 结构
- [x] 建立新后端 API 骨架、鉴权、用户模型、管理接口
- [x] 建立新前端 App Shell、登录页、一级导航、模块页骨架
- [x] 挂载旧 Flask 到 `/legacy`

### M2 数据与迁移
- [x] 建立新数据模型：用户、会话、自选、策略、信号、模拟账户、报告、调参历史
- [x] 建立 Alembic 基础目录与初始迁移
- [x] 建立旧 SQLite -> 新模型导入脚本
- [ ] 将旧日报、bundle、调参快照等文件型资产迁入新体系

### M3 实时与 Worker
- [x] 建立 WebSocket `/ws/v1/stream`
- [x] 建立 `market_engine` / `strategy_engine` / `report_jobs` worker stub
- [ ] 将旧行情抓取与策略执行循环迁入新 worker
- [ ] 使用 Redis 做事件分发和实时广播

### M4 业务能力对齐
- [x] 新 API 覆盖 auth / me / dashboard / market / watchlist / strategy / signals / paper / reports / diagnostics / tuning / admin / health
- [ ] 将旧历史查询、周期报告、日报对比、preflight、edge diagnostics 的真实逻辑桥接到新 API
- [ ] 将旧策略参数调优逻辑迁移为用户私有配置，而不是全局运行态
- [ ] 将旧 signal explain、日报生成、bundle 生成结果对齐到新前端页面

### M5 前端体验
- [x] 新首页信息架构雏形
- [x] Signals / Paper / Reports / Diagnostics / Strategy / Watchlist / Admin 页面骨架
- [ ] 接入实时 WS 数据流更新首页与信号页
- [ ] 细化表单、图表、空态、错误态、Skeleton 与模块内交互
- [ ] 做代码分割，降低首包大小

### M6 上线与接力
- [x] 新脚本：启动 API / Worker / 前端构建 / 本地开发说明
- [x] 自动任务目录 `.autonomous/renfu-next-stack/`
- [x] 保存执行计划与进度文档
- [ ] 扩展部署脚本到新前后端分离流程
- [ ] 完成生产 systemd / Nginx 配置模板

## 当前最优先剩余工作
1. 把新 Reports / Diagnostics 接口换成旧系统真实统计逻辑，而不是占位结果。
2. 将 Worker stub 替换为旧行情与策略逻辑迁移版。
3. 为前端接入实时 WS，减少纯轮询依赖。
4. 继续做前端模块的结构化类型和页面细化。
5. 补全迁移、部署和生产配置。
