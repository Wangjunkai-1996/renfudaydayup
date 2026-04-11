# Renfu Next 当前进度

更新日期：2026-03-09

## 本轮完成
- 强化 legacy bridge，打通 Dashboard / Market / Signals / Paper / Strategy / Reports / Diagnostics 的真实桥接链路
- 新增并修正后端接口：工作区、自选排序、设置、信号详情、纸面订单、策略快照与回滚等
- App Shell、Dashboard、Market、Signals、Paper 已进入中文业务态展示
- Reports、Diagnostics、Strategy、Watchlist、Settings、Admin 已从骨架页升级为可用版工作台页面
- 新增设置接口 `/api/v1/settings/logout-all`，前端已接入安全登出所有会话
- `frontend` 已通过 `vue-tsc` 类型检查

## 当前可用能力
- Dashboard / Market 可作为新首页和盯盘主入口
- Signals 可查看实时信号、详情和 explain
- Paper 可查看账户、持仓、订单并修改底仓配置
- Reports 可看历史、生成日报与 bundle、做日报对比、看周期报告
- Diagnostics 可查看 preflight / slot / edge，并应用 tuning patch
- Strategy / Watchlist / Settings / Admin 均可在新 UI 内完成主要动作

## 仍待完成
- worker 仍有 stub 成分，尚未彻底替换成 legacy 的真实长循环执行链路
- WebSocket 仍以定时快照为主，后续要继续收紧到更细颗粒事件流
- Playwright E2E 与更完整的回归测试还没补完
- 部署脚本、Nginx、systemd 的生产模板仍需补齐
- `WorkbenchChart` 相关 chunk 仍偏大，后续要做图表模块拆包

## 已完成验证
- `cd frontend && npx vue-tsc --noEmit -p tsconfig.json`
- `cd frontend && npm run build`
- `cd frontend && npm run test:run`
- `backend/.venv/bin/pytest backend/tests`

## 下一步建议
1. 跑 `cd frontend && npm run build`
2. 跑 `cd backend && pytest`
3. 本地联调所有一级导航页面
4. 补 E2E 与部署链路
