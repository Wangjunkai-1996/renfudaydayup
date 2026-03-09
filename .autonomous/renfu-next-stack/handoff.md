# Handoff

## 本任务目录
- `.autonomous/renfu-next-stack/task_list.md`
- `.autonomous/renfu-next-stack/progress.md`
- `.autonomous/renfu-next-stack/handoff.md`

## 快速恢复工作环境
1. 拉取最新代码。
2. 进入仓库根目录。
3. 启动新后端：`./scripts/run_next_api.sh`
4. 启动前端开发：`cd frontend && npm install && npm run dev`
5. 如需导入旧数据：`./scripts/migrate_legacy_to_postgres.py`
6. 访问：
   - 新前端：`http://localhost:5173`
   - 新 API：`http://localhost:9000/api/v1`
   - 旧系统：`http://localhost:9000/legacy`

## 建议接力顺序
1. 先读 `docs/RENFU_NEXT_EXECUTION_PLAN.md`
2. 再读 `docs/RENFU_NEXT_PROGRESS.md`
3. 再看 `.autonomous/renfu-next-stack/task_list.md`
4. 再从 `backend/app/api/v1/reports.py` 和 `backend/app/api/v1/diagnostics.py` 开始继续桥接旧逻辑

## 当前关键文件
- 新后端入口：`backend/app/main.py`
- 新前端路由：`frontend/src/app/router.ts`
- 新应用壳层：`frontend/src/shared/layouts/AppShell.vue`
- 新数据模型：`backend/app/models/entities.py`
- 迁移脚本：`scripts/migrate_legacy_to_postgres.py`
