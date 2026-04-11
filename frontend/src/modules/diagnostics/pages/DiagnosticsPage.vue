<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query';
import { computed, ref, watch } from 'vue';

import { apiClient } from '@/shared/api/client';
import type { TuningHistoryItem, TuningSuggestionPayload } from '@/shared/api/types';
import { formatDateTime, formatNumber } from '@/shared/lib/format';
import AppCard from '@/shared/ui/AppCard.vue';
import EmptyPanel from '@/shared/ui/EmptyPanel.vue';
import ErrorPanel from '@/shared/ui/ErrorPanel.vue';
import LoadingSkeleton from '@/shared/ui/LoadingSkeleton.vue';
import MetricCard from '@/shared/ui/MetricCard.vue';
import MiniStatList from '@/shared/ui/MiniStatList.vue';
import PageHeader from '@/shared/ui/PageHeader.vue';
import StateBadge from '@/shared/ui/StateBadge.vue';

interface LooseRecord {
  [key: string]: unknown;
}

const queryClient = useQueryClient();
const today = new Date().toISOString().slice(0, 10);
const targetDate = ref(today);
const baselineDate = ref('');
const patchDraft = ref('{}');
const tuningNote = ref('');
const pageError = ref('');
const feedback = ref('');

const preflightQuery = useQuery({
  queryKey: ['diag-preflight', targetDate],
  queryFn: () => apiClient.get<LooseRecord>(`/api/v1/diagnostics/preflight?date=${targetDate.value}`),
});

const slotQuery = useQuery({
  queryKey: ['diag-slot', targetDate],
  queryFn: () => apiClient.get<LooseRecord>(`/api/v1/diagnostics/slot-performance?date=${targetDate.value}`),
});

const edgeQuery = useQuery({
  queryKey: ['diag-edge', targetDate],
  queryFn: () => apiClient.get<LooseRecord>(`/api/v1/diagnostics/edge-diagnostics?date=${targetDate.value}`),
});

const tuningQuery = useQuery({
  queryKey: ['diag-tuning', targetDate, baselineDate],
  queryFn: () => {
    const params = new URLSearchParams({ date: targetDate.value });
    if (baselineDate.value) {
      params.set('baseline', baselineDate.value);
    }
    return apiClient.get<TuningSuggestionPayload>(`/api/v1/tuning/suggest?${params.toString()}`);
  },
});

const historyQuery = useQuery({
  queryKey: ['diag-tuning-history'],
  queryFn: () => apiClient.get<{ items?: TuningHistoryItem[]; source?: string }>('/api/v1/tuning/history'),
});

const applyMutation = useMutation({
  mutationFn: (payload: { patch: LooseRecord; note: string }) => apiClient.post('/api/v1/tuning/apply', payload),
  onSuccess: async () => {
    feedback.value = '调优补丁已提交，策略配置与历史记录正在刷新。';
    pageError.value = '';
    tuningNote.value = '';
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['diag-tuning-history'] }),
      queryClient.invalidateQueries({ queryKey: ['diag-tuning'] }),
      queryClient.invalidateQueries({ queryKey: ['strategy-config'] }),
      queryClient.invalidateQueries({ queryKey: ['dashboard-diagnostics'] }),
    ]);
  },
  onError: (error) => {
    pageError.value = error instanceof Error ? error.message : '应用调优失败';
  },
});

function asRecord(value: unknown): LooseRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as LooseRecord : {};
}

function asRecordList(value: unknown): LooseRecord[] {
  return Array.isArray(value) ? value.filter((item): item is LooseRecord => Boolean(item) && typeof item === 'object' && !Array.isArray(item)) : [];
}

function displayValue(value: unknown): string {
  if (value == null) {
    return '--';
  }
  if (typeof value === 'number') {
    return formatNumber(value, 2);
  }
  if (typeof value === 'boolean') {
    return value ? '是' : '否';
  }
  if (Array.isArray(value)) {
    if (!value.length) {
      return '0 项';
    }
    if (value.every((item) => typeof item !== 'object')) {
      return value.map((item) => String(item)).join(' / ');
    }
    return `${value.length} 项`;
  }
  if (typeof value === 'object') {
    return `${Object.keys(value as LooseRecord).length} 个字段`;
  }
  return String(value);
}

function toMiniStats(value: unknown, limit = 6): Array<{ label: string; value: string }> {
  return Object.entries(asRecord(value))
    .slice(0, limit)
    .map(([label, raw]) => ({ label, value: displayValue(raw) }));
}

const preflightAssessment = computed(() => asRecord(preflightQuery.data.value?.assessment));
const slotRows = computed(() => asRecordList(slotQuery.data.value?.performance));
const slotHints = computed(() => {
  const hints = slotQuery.data.value?.hints;
  return Array.isArray(hints) ? hints.map((item) => String(item)) : [];
});
const edgeDiagnostics = computed(() => asRecord(edgeQuery.data.value?.diagnostics ?? edgeQuery.data.value));
const edgeSuggestionRows = computed(() => asRecordList(edgeDiagnostics.value.suggestions ?? edgeDiagnostics.value.items));
const tuningAssessment = computed(() => asRecord(tuningQuery.data.value?.assessment));
const tuningPerformance = computed(() => asRecord(tuningQuery.data.value?.performance));
const tuningHints = computed(() => {
  const hints = tuningQuery.data.value?.hints;
  return Array.isArray(hints) ? hints.map((item) => String(item)) : [];
});
const tuningHistory = computed(() => historyQuery.data.value?.items ?? []);
const tuningPatchPreview = computed(() => {
  const direct = asRecord(tuningQuery.data.value?.suggestion);
  if (Object.keys(direct).length) {
    return direct;
  }
  const diagnostics = asRecord(tuningQuery.data.value?.diagnostics);
  return asRecord(diagnostics.patch_preview);
});

watch(
  tuningPatchPreview,
  (value) => {
    patchDraft.value = JSON.stringify(value, null, 2);
  },
  { immediate: true },
);


async function refreshAll() {
  await Promise.all([preflightQuery.refetch(), slotQuery.refetch(), edgeQuery.refetch(), tuningQuery.refetch()]);
}
function applyPatch() {
  try {
    const patch = JSON.parse(patchDraft.value) as LooseRecord;
    pageError.value = '';
    applyMutation.mutate({ patch, note: tuningNote.value.trim() });
  } catch {
    pageError.value = '调优补丁不是合法 JSON，请先修正后再应用。';
  }
}
</script>

<template>
  <PageHeader title="诊断与调优" subtitle="Preflight、时段表现、边际诊断和调优建议统一在这里查看与执行。" />

  <div class="mb-6 grid gap-4 md:grid-cols-4">
    <MetricCard label="诊断日期" :value="targetDate" helper="所有诊断默认围绕该交易日" tone="brand" />
    <MetricCard label="时段样本" :value="String(slotRows.length)" helper="已返回的时段表现条目" :tone="slotRows.length ? 'positive' : 'default'" />
    <MetricCard label="调优提示" :value="String(tuningHints.length)" helper="策略建议和风险提示数量" :tone="tuningHints.length ? 'positive' : 'default'" />
    <MetricCard label="历史记录" :value="String(tuningHistory.length)" helper="已保存的调优历史" />
  </div>

  <div v-if="pageError" class="mb-4">
    <ErrorPanel :message="pageError" />
  </div>
  <div v-else-if="feedback" class="mb-4 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
    {{ feedback }}
  </div>

  <div class="mb-6 grid gap-3 md:grid-cols-[1fr_1fr_auto]">
    <input v-model="targetDate" type="date" class="input-base" />
    <input v-model="baselineDate" type="date" class="input-base" placeholder="可选：基准日" />
    <button class="btn-secondary" @click="refreshAll">刷新诊断</button>
  </div>

  <div class="grid gap-4 xl:grid-cols-[1fr_1fr]">
    <AppCard title="Preflight 评估" subtitle="查看当天策略体检结果、完成情况和关键说明。">
      <div v-if="preflightQuery.isLoading.value"><LoadingSkeleton :lines="6" height="18px" /></div>
      <template v-else>
        <div class="flex flex-wrap gap-2">
          <StateBadge :label="String(preflightQuery.data.value?.source || 'unknown') === 'legacy' ? 'Legacy 真结果' : 'Next 结果'" :tone="String(preflightQuery.data.value?.source || '') === 'legacy' ? 'brand' : 'default'" />
          <StateBadge :label="String(preflightAssessment.level || preflightAssessment.status || 'ok')" tone="positive" />
        </div>
        <div class="mt-4 text-sm text-slate-300">{{ String(preflightAssessment.message || preflightAssessment.headline || '诊断已完成，请根据下方指标查看风险边界。') }}</div>
        <div class="mt-4" v-if="toMiniStats(preflightAssessment).length">
          <MiniStatList :items="toMiniStats(preflightAssessment)" />
        </div>
        <EmptyPanel v-else title="暂无更多 preflight 指标" description="当前返回内容较少，但诊断链路已接通。" />
      </template>
    </AppCard>

    <AppCard title="边际诊断" subtitle="观察 summary、suggestions 和重点边界项。">
      <div v-if="edgeQuery.isLoading.value"><LoadingSkeleton :lines="6" height="18px" /></div>
      <template v-else>
        <div class="text-sm text-slate-300">{{ String(edgeDiagnostics.summary || edgeDiagnostics.message || edgeDiagnostics.headline || '边际诊断结果已生成。') }}</div>
        <div class="mt-4" v-if="toMiniStats(edgeDiagnostics).length">
          <MiniStatList :items="toMiniStats(edgeDiagnostics, 8)" />
        </div>
        <div v-if="edgeSuggestionRows.length" class="mt-4 overflow-x-auto">
          <table class="panel-table">
            <thead>
              <tr>
                <th>字段</th>
                <th>建议值</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, index) in edgeSuggestionRows" :key="String(item.path || item.field || index)">
                <td>{{ String(item.path || item.field || item.key || '--') }}</td>
                <td>{{ displayValue(item.value ?? item.target ?? item.next_value) }}</td>
                <td class="text-slate-400">{{ String(item.reason || item.note || item.comment || '--') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </AppCard>
  </div>

  <div class="mt-6 grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
    <AppCard title="时段表现" subtitle="将时段样本、胜率和建议提示业务化展示，不再直接输出 JSON。">
      <div v-if="slotQuery.isLoading.value"><LoadingSkeleton :lines="8" height="18px" /></div>
      <div v-else-if="slotRows.length" class="space-y-4">
        <div class="overflow-x-auto">
          <table class="panel-table">
            <thead>
              <tr>
                <th>时段</th>
                <th>胜率</th>
                <th>样本数</th>
                <th>备注</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, index) in slotRows" :key="String(item.slot || item.time_slot || index)">
                <td>{{ String(item.slot || item.time_slot || item.name || '--') }}</td>
                <td>{{ displayValue(item.win_rate ?? item.hit_rate ?? item.success_rate) }}</td>
                <td>{{ displayValue(item.total ?? item.count ?? item.sample_size) }}</td>
                <td class="text-slate-400">{{ String(item.summary || item.note || item.comment || '--') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="slotHints.length" class="flex flex-wrap gap-2">
          <StateBadge v-for="hint in slotHints" :key="hint" :label="hint" tone="warning" />
        </div>
      </div>
      <EmptyPanel v-else title="暂无时段表现数据" description="当前日期没有返回可展示的时段样本。" />
    </AppCard>

    <AppCard title="调优建议与应用" subtitle="先生成建议，再按需修改补丁并直接应用到当前策略。">
      <div v-if="tuningQuery.isLoading.value"><LoadingSkeleton :lines="8" height="18px" /></div>
      <template v-else>
        <div class="space-y-4">
          <div v-if="toMiniStats(tuningAssessment).length">
            <div class="mb-3 text-sm font-semibold text-white">诊断摘要</div>
            <MiniStatList :items="toMiniStats(tuningAssessment, 6)" />
          </div>

          <div v-if="toMiniStats(tuningPerformance).length">
            <div class="mb-3 text-sm font-semibold text-white">表现快照</div>
            <MiniStatList :items="toMiniStats(tuningPerformance, 6)" />
          </div>

          <div v-if="tuningHints.length" class="flex flex-wrap gap-2">
            <StateBadge v-for="hint in tuningHints" :key="hint" :label="hint" tone="brand" />
          </div>

          <textarea v-model="patchDraft" class="min-h-[220px] w-full rounded-2xl border border-slate-700 bg-slate-950/70 p-4 text-sm text-slate-200 outline-none focus:border-indigo-400"></textarea>
          <input v-model="tuningNote" class="input-base" placeholder="本次调优备注（可选）" />
          <button class="btn-primary" @click="applyPatch">应用本次调优</button>
        </div>
      </template>
    </AppCard>
  </div>

  <div class="mt-6 grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
    <AppCard title="调优历史" subtitle="记录每次 patch、说明和生成时间，便于后续回看。">
      <div v-if="historyQuery.isLoading.value"><LoadingSkeleton :lines="6" height="18px" /></div>
      <div v-else-if="tuningHistory.length" class="space-y-3">
        <div v-for="item in tuningHistory" :key="String(item.id || item.created_at || item.date)" class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          <div class="flex items-start justify-between gap-3">
            <div>
              <div class="text-sm font-semibold text-white">{{ String(item.action || 'apply') }}</div>
              <div class="mt-1 text-xs text-slate-500">{{ formatDateTime(item.created_at || item.generated_at || item.date || '') }}</div>
            </div>
            <StateBadge :label="String(item.path || item.file || 'patch').slice(0, 20) || 'patch'" tone="default" />
          </div>
          <div class="mt-3 text-sm text-slate-300">{{ item.note || '无备注，按默认建议应用。' }}</div>
        </div>
      </div>
      <EmptyPanel v-else title="暂无调优历史" description="应用第一次调优后，这里会开始沉淀历史记录。" />
    </AppCard>

    <AppCard title="使用说明" subtitle="当前阶段采用旧逻辑优先桥接，保障 legacy_admin 可直接看到真实诊断结果。">
      <div class="space-y-3 text-sm text-slate-300">
        <div class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">如果你是 <span class="font-semibold text-white">legacy_admin</span>，页面会优先消费 legacy 真实诊断、报告和调优建议。</div>
        <div class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">非 legacy 用户先走新模型，但接口结构已经与 legacy 对齐，方便后续平滑迁移。</div>
        <div class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">应用调优后会同步刷新策略配置页、Dashboard 诊断摘要和调优历史，不需要手动刷新整页。</div>
      </div>
    </AppCard>
  </div>
</template>
