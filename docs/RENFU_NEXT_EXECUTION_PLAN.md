# Renfu Next UI 全导航可用版执行计划

更新日期：2026-03-09

## 目标
- 把 `frontend/` 从“可打开的前端骨架”推进到“全导航可用版”。
- 把 `backend/` 从“新 API 壳层”推进到“legacy bridge + 新用户模型并行承载真实数据”。
- 让新 UI 可以承担日常盯盘、查信号、看账户、看报告、做诊断、调参数、管用户的主要操作。
- 继续保留 `/legacy` 作为对照和回退入口，但不再回填新功能。

## 已锁定实现原则
- 前端：Vue 3 + Vite + TypeScript + Pinia + Vue Query + Tailwind + ECharts
- 后端：FastAPI + SQLAlchemy 2.x + Alembic
- 数据路线：优先接 legacy 真实逻辑，`legacy_admin` 优先桥接旧结果
- UI 原则：桌面优先、深色主题、中文完整、卡片化和业务化展示
- 运行方式：新前后端与 legacy 并行，Nginx 负责静态资源与 API / WS 反代

## 阶段状态

### Phase 1 — 清骨架、统一全局层
- [x] App Shell 改为中文导航与正式状态条
- [x] WebSocket 连接态、交易时段、Legacy/Next 模式状态显性展示
- [x] 新增统一状态组件：`MetricCard`、`EmptyPanel`、`ErrorPanel`、`LoadingSkeleton`、`WorkbenchChart` 等
- [x] 去掉裸 `pre/json` 占位展示和大块英文骨架文案

### Phase 2 — Dashboard / Market 真正可用
- [x] Dashboard 接入真实 summary、诊断摘要、工作区预览和实时信号流
- [x] Market 接入 `market/workbench`、上下文面板和自选板块
- [x] `WorkbenchChart` 取代旧 `PulseChart` 的占位职责
- [x] Watchlist 排序进入新工作区链路

### Phase 3 — Signals / Paper 业务闭环
- [x] Signals 列表、筛选、详情抽屉、explain 展示可用
- [x] Paper 账户摘要、持仓、订单、底仓配置可用
- [x] WebSocket 扩展到 `market_tick`、`watchlist_quote`、`signal_updated`、`diagnostic_updated` 等事件
- [ ] Worker 真实交易联动仍待继续用 legacy 运行逻辑替换 stub

### Phase 4 — Reports / Diagnostics / Strategy 对齐
- [x] Reports 页面改为真实历史统计、日报、bundle、对比、周期报告展示
- [x] Diagnostics 页面改为 preflight、slot performance、edge diagnostics、tuning 历史与 patch 应用工作台
- [x] Strategy 页面改为“结构化表单优先 + JSON 高级模式兜底”
- [x] `backend/app/domain/legacy_facade.py` 已补齐报告、诊断、调优、工作区、信号 explain 等桥接能力
- [ ] 真实 worker/Redis 事件分发尚未完全替换当前轮询式快照推送

### Phase 5 — Watchlist / Settings / Admin / Polish
- [x] Watchlist 页面可搜索、添加、删除、排序，并同步工作区默认顺序
- [x] Settings 页面可修改用户名、密码、通知偏好，并新增“安全登出所有会话”接口
- [x] Admin 页面可创建用户、启停账号、重置密码、查看系统健康
- [x] 关键页面统一补上空态、错误态、加载态
- [ ] Playwright E2E 仍待补齐
- [ ] 部署脚本与生产 Nginx / systemd 模板仍待补齐

## 本轮已完成的关键落地

### 后端
- 强化 legacy bridge：工作区、上下文、信号详情 / explain、策略配置 / 快照 / 回滚、纸面账户、报告、诊断、调优全部进入统一 schema 输出
- 市场与自选接口支持：`/api/v1/market/workbench`、`/api/v1/market/context/{symbol}`、`/api/v1/watchlist/reorder`
- 设置接口支持：账号资料、密码修改、通知配置，以及新增 `/api/v1/settings/logout-all`
- WebSocket 扩展：`market_snapshot`、`market_tick`、`watchlist_quote`、`signal_updated`、`diagnostic_updated`、`system_status`

### 前端
- Dashboard：首屏指标、工作区预览、实时信号流、诊断摘要、快捷入口
- Market：股票 tabs、主图、上下文、自选排序、市场脉搏侧栏
- Signals：筛选、详情、explain、图表视窗
- Paper：账户摘要、持仓、订单、底仓配置
- Reports：历史统计、日报、bundle、差异对比、周期报告
- Diagnostics：preflight、slot performance、edge diagnostics、tuning patch 与历史
- Strategy：结构化参数编辑、高级 JSON、快照、回滚
- Watchlist：搜索、添加、删除、上移/下移排序、默认首屏同步
- Settings：账户资料、密码、通知偏好、安全登出所有会话
- Admin：用户创建、启停、重置密码、系统健康

## 当前剩余工作
1. 把 worker stub 继续替换为 legacy 真实行情和策略执行链路
2. 将 WebSocket 从“快照驱动”进一步升级为更细颗粒的事件分发
3. 补齐 Playwright E2E：登录、Watchlist 排序、Market 切股看图、Signals 详情、Paper、Reports、Admin
4. 扩展 `scripts/` 部署脚本，补 systemd / Nginx 生产模板
5. 完成新旧结果对照与性能回归，确认默认入口切换条件

## 接力入口
- 前端核心目录：`frontend/src/modules/`
- 后端桥接核心：`backend/app/domain/legacy_facade.py`
- API 汇总：`backend/app/api/v1/`
- WebSocket：`backend/app/ws/router.py`
- 长任务进度：`.autonomous/renfu-next-ui-v1/`

## 继续推进时建议先看
1. `.autonomous/renfu-next-ui-v1/task_list.md`
2. `.autonomous/renfu-next-ui-v1/progress.md`
3. `docs/RENFU_NEXT_PROGRESS.md`
