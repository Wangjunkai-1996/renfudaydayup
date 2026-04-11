<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query';
import { computed, ref, watch } from 'vue';

import { apiClient } from '@/shared/api/client';
import { formatDateTime, formatNumber } from '@/shared/lib/format';
import AppCard from '@/shared/ui/AppCard.vue';
import EmptyPanel from '@/shared/ui/EmptyPanel.vue';
import ErrorPanel from '@/shared/ui/ErrorPanel.vue';
import LoadingSkeleton from '@/shared/ui/LoadingSkeleton.vue';
import MetricCard from '@/shared/ui/MetricCard.vue';
import MiniStatList from '@/shared/ui/MiniStatList.vue';
import PageHeader from '@/shared/ui/PageHeader.vue';
import StateBadge from '@/shared/ui/StateBadge.vue';

interface StrategyConfigView {
  id: string;
  user_id: string;
  config_json: Record<string, unknown>;
  updated_at: string;
}

interface StrategySnapshotView {
  id: string;
  label: string;
  config_json: Record<string, unknown>;
  created_at: string;
}

const queryClient = useQueryClient();
const advancedMode = ref(false);
const snapshotLabel = ref('');
const rawConfig = ref('{}');
const feedback = ref('');
const pageError = ref('');

const riskProfile = ref('balanced');
const maxStocks = ref(3);
const edgeMin = ref(0.12);
const maxPositionPct = ref(25);
const stopLossPct = ref(2.5);
const morningEnabled = ref(true);
const afternoonEnabled = ref(true);
const focusSymbols = ref('');
const notes = ref('');

const configQuery = useQuery({
  queryKey: ['strategy-config'],
  queryFn: () => apiClient.get<StrategyConfigView>('/api/v1/strategy/config'),
});

const snapshotQuery = useQuery({
  queryKey: ['strategy-snapshots'],
  queryFn: () => apiClient.get<StrategySnapshotView[]>('/api/v1/strategy/snapshots'),
});

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function readNumber(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function readBoolean(value: unknown, fallback = true): boolean {
  return typeof value === 'boolean' ? value : fallback;
}

function readString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function syncFromConfig(config: Record<string, unknown>) {
  const sessions = asRecord(config.sessions);
  riskProfile.value = readString(config.risk_profile, 'balanced');
  maxStocks.value = readNumber(config.max_stocks, 3);
  edgeMin.value = readNumber(config.edge_min, 0.12);
  maxPositionPct.value = readNumber(config.max_position_pct, 25);
  stopLossPct.value = readNumber(config.stop_loss_pct, 2.5);
  morningEnabled.value = readBoolean(sessions.morning, true);
  afternoonEnabled.value = readBoolean(sessions.afternoon, true);
  focusSymbols.value = Array.isArray(config.focus_symbols) ? config.focus_symbols.map((item) => String(item)).join(', ') : '';
  notes.value = readString(config.notes, '');
  rawConfig.value = JSON.stringify(config, null, 2);
}

watch(
  () => configQuery.data.value?.config_json,
  (value) => {
    syncFromConfig(asRecord(value));
  },
  { immediate: true },
);

const snapshots = computed(() => snapshotQuery.data.value ?? []);
const parsedConfig = computed<Record<string, unknown>>(() => {
  try {
    return JSON.parse(rawConfig.value) as Record<string, unknown>;
  } catch {
    return {};
  }
});

const summaryItems = computed(() => [
  { label: '风险档位', value: riskProfile.value },
  { label: '最大持股数', value: String(maxStocks.value) },
  { label: '边际阈值', value: formatNumber(edgeMin.value, 2) },
  { label: '单股上限', value: `${formatNumber(maxPositionPct.value, 0)}%` },
  { label: '止损阈值', value: `${formatNumber(stopLossPct.value, 1)}%` },
  { label: '焦点股', value: focusSymbols.value || '未限定' },
]);

const saveMutation = useMutation({
  mutationFn: (config_json: Record<string, unknown>) => apiClient.put<StrategyConfigView>('/api/v1/strategy/config', { config_json }),
  onSuccess: async (payload) => {
    feedback.value = '策略配置已保存。';
    pageError.value = '';
    syncFromConfig(payload.config_json || {});
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['strategy-config'] }),
      queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] }),
    ]);
  },
  onError: (error) => {
    pageError.value = error instanceof Error ? error.message : '保存策略失败';
  },
});

const snapshotMutation = useMutation({
  mutationFn: () => apiClient.post<StrategySnapshotView>('/api/v1/strategy/snapshots', { label: snapshotLabel.value.trim() || `快照 ${new Date().toLocaleString('zh-CN')}` }),
  onSuccess: async () => {
    feedback.value = '策略快照已保存。';
    pageError.value = '';
    snapshotLabel.value = '';
    await queryClient.invalidateQueries({ queryKey: ['strategy-snapshots'] });
  },
  onError: (error) => {
    pageError.value = error instanceof Error ? error.message : '保存快照失败';
  },
});

const rollbackMutation = useMutation({
  mutationFn: (snapshotId: string) => apiClient.post<StrategyConfigView>('/api/v1/strategy/rollback', { snapshot_id: snapshotId }),
  onSuccess: async (payload) => {
    feedback.value = '已回滚到所选快照。';
    pageError.value = '';
    syncFromConfig(payload.config_json || {});
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['strategy-config'] }),
      queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] }),
    ]);
  },
  onError: (error) => {
    pageError.value = error instanceof Error ? error.message : '回滚快照失败';
  },
});

function buildStructuredConfig(): Record<string, unknown> {
  const base = asRecord(parsedConfig.value);
  return {
    ...base,
    risk_profile: riskProfile.value,
    max_stocks: Number(maxStocks.value),
    edge_min: Number(edgeMin.value),
    max_position_pct: Number(maxPositionPct.value),
    stop_loss_pct: Number(stopLossPct.value),
    notes: notes.value.trim(),
    focus_symbols: focusSymbols.value
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean),
    sessions: {
      ...asRecord(base.sessions),
      morning: morningEnabled.value,
      afternoon: afternoonEnabled.value,
    },
  };
}

function saveStructuredConfig() {
  saveMutation.mutate(buildStructuredConfig());
}

function saveAdvancedConfig() {
  try {
    saveMutation.mutate(JSON.parse(rawConfig.value) as Record<string, unknown>);
  } catch {
    pageError.value = '高级 JSON 配置无法解析，请检查后再保存。';
  }
}
</script>

<template>
  <PageHeader title="策略参数" subtitle="结构化编辑常用策略参数，并保留高级 JSON 模式做兜底。" />

  <div class="mb-6 grid gap-4 md:grid-cols-4">
    <MetricCard label="当前档位" :value="riskProfile" helper="对应当前风险画像" tone="brand" />
    <MetricCard label="最大持股数" :value="String(maxStocks)" helper="超过上限时会约束持仓扩张" />
    <MetricCard label="快照数量" :value="String(snapshots.length)" helper="可随时回滚到历史版本" :tone="snapshots.length ? 'positive' : 'default'" />
    <MetricCard label="最近更新" :value="configQuery.data.value?.updated_at ? formatDateTime(configQuery.data.value.updated_at) : '--'" helper="保存后自动刷新" />
  </div>

  <div v-if="pageError" class="mb-4">
    <ErrorPanel :message="pageError" />
  </div>
  <div v-else-if="feedback" class="mb-4 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
    {{ feedback }}
  </div>

  <div class="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
    <AppCard title="结构化配置" subtitle="常用参数直接编辑，避免普通用户频繁手改 JSON。">
      <div v-if="configQuery.isLoading.value"><LoadingSkeleton :lines="10" height="18px" /></div>
      <template v-else>
        <div class="grid gap-4 md:grid-cols-2">
          <label class="block text-sm text-slate-300">
            <div class="mb-2 font-medium text-white">风险档位</div>
            <select v-model="riskProfile" class="input-base">
              <option value="conservative">保守</option>
              <option value="balanced">均衡</option>
              <option value="aggressive">积极</option>
            </select>
          </label>
          <label class="block text-sm text-slate-300">
            <div class="mb-2 font-medium text-white">最大持股数</div>
            <input v-model.number="maxStocks" type="number" min="1" max="20" class="input-base" />
          </label>
          <label class="block text-sm text-slate-300">
            <div class="mb-2 font-medium text-white">边际阈值</div>
            <input v-model.number="edgeMin" type="number" min="0" step="0.01" class="input-base" />
          </label>
          <label class="block text-sm text-slate-300">
            <div class="mb-2 font-medium text-white">单股仓位上限（%）</div>
            <input v-model.number="maxPositionPct" type="number" min="0" step="1" class="input-base" />
          </label>
          <label class="block text-sm text-slate-300">
            <div class="mb-2 font-medium text-white">止损阈值（%）</div>
            <input v-model.number="stopLossPct" type="number" min="0" step="0.1" class="input-base" />
          </label>
          <label class="block text-sm text-slate-300">
            <div class="mb-2 font-medium text-white">焦点股票</div>
            <input v-model="focusSymbols" class="input-base" placeholder="用逗号分隔多个代码" />
          </label>
        </div>

        <div class="mt-4 grid gap-3 md:grid-cols-2">
          <button class="rounded-2xl border border-slate-700 px-4 py-3 text-left text-sm text-white" :class="morningEnabled ? 'bg-indigo-500/10 border-indigo-500/40' : 'bg-slate-950/60'" @click="morningEnabled = !morningEnabled">
            上午时段 {{ morningEnabled ? '已启用' : '已关闭' }}
          </button>
          <button class="rounded-2xl border border-slate-700 px-4 py-3 text-left text-sm text-white" :class="afternoonEnabled ? 'bg-indigo-500/10 border-indigo-500/40' : 'bg-slate-950/60'" @click="afternoonEnabled = !afternoonEnabled">
            下午时段 {{ afternoonEnabled ? '已启用' : '已关闭' }}
          </button>
        </div>

        <div class="mt-4">
          <div class="mb-2 text-sm font-medium text-white">备注</div>
          <textarea v-model="notes" class="min-h-[120px] w-full rounded-2xl border border-slate-700 bg-slate-950/70 p-4 text-sm text-slate-200 outline-none focus:border-indigo-400" placeholder="记录当前参数的适用场景、调优依据或风险提示"></textarea>
        </div>

        <div class="mt-4">
          <MiniStatList :items="summaryItems" />
        </div>

        <div class="mt-4 flex flex-wrap items-center gap-3">
          <button class="btn-primary" @click="saveStructuredConfig">保存结构化配置</button>
          <button class="btn-secondary" @click="advancedMode = !advancedMode">{{ advancedMode ? '收起高级模式' : '打开高级 JSON 模式' }}</button>
        </div>

        <div v-if="advancedMode" class="mt-4 rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          <div class="mb-3 flex items-center justify-between gap-3">
            <div>
              <div class="text-sm font-semibold text-white">高级 JSON 模式</div>
              <div class="mt-1 text-sm text-slate-400">适合处理结构化表单未覆盖的字段，保存前会先做 JSON 解析。</div>
            </div>
            <StateBadge label="高级模式" tone="warning" />
          </div>
          <textarea v-model="rawConfig" class="min-h-[240px] w-full rounded-2xl border border-slate-700 bg-slate-950/70 p-4 text-sm text-slate-200 outline-none focus:border-indigo-400"></textarea>
          <div class="mt-4 flex gap-3">
            <button class="btn-primary" @click="saveAdvancedConfig">保存 JSON 配置</button>
            <button class="btn-secondary" @click="syncFromConfig(parsedConfig)">用当前 JSON 回填结构化表单</button>
          </div>
        </div>
      </template>
    </AppCard>

    <AppCard title="策略快照" subtitle="保存关键版本，出问题时一键回滚。">
      <div class="flex gap-3">
        <input v-model="snapshotLabel" class="input-base" placeholder="例如：午盘降仓版 / 强趋势版" />
        <button class="btn-primary" @click="snapshotMutation.mutate()">保存快照</button>
      </div>

      <div class="mt-4" v-if="snapshotQuery.isLoading.value">
        <LoadingSkeleton :lines="6" height="64px" />
      </div>
      <div v-else-if="snapshots.length" class="space-y-3">
        <div v-for="snapshot in snapshots" :key="snapshot.id" class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          <div class="flex items-start justify-between gap-3">
            <div>
              <div class="text-sm font-semibold text-white">{{ snapshot.label }}</div>
              <div class="mt-1 text-xs text-slate-500">{{ formatDateTime(snapshot.created_at) }}</div>
              <div class="mt-3 flex flex-wrap gap-2">
                <StateBadge :label="String(snapshot.config_json.risk_profile || 'balanced')" tone="brand" />
                <StateBadge :label="`持股上限 ${String(snapshot.config_json.max_stocks || '--')}`" tone="default" />
              </div>
            </div>
            <button class="rounded-2xl bg-indigo-500/20 px-4 py-2 text-sm font-medium text-indigo-100 hover:bg-indigo-500/30" @click="rollbackMutation.mutate(snapshot.id)">回滚到此版本</button>
          </div>
        </div>
      </div>
      <EmptyPanel v-else title="还没有策略快照" description="保存第一次快照后，这里会沉淀你的版本历史。" />
    </AppCard>
  </div>
</template>
