<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query';
import { computed, ref } from 'vue';

import { apiClient } from '@/shared/api/client';
import type {
  BundlePayload,
  ComparePayload,
  DailyReportListItem,
  DailyReportPayload,
  PeriodicReportPayload,
  ReportHistoryPayload,
} from '@/shared/api/types';
import { formatDate, formatDateTime } from '@/shared/lib/format';
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
const reportDate = ref(today);
const compareDate = ref(today);
const baselineDate = ref(today);
const pageError = ref('');
const feedback = ref('');

const historyQuery = useQuery({
  queryKey: ['reports-history'],
  queryFn: () => apiClient.get<ReportHistoryPayload>('/api/v1/reports/history'),
});

const listQuery = useQuery({
  queryKey: ['reports-daily-list'],
  queryFn: () => apiClient.get<{ items?: DailyReportListItem[]; source?: string }>('/api/v1/reports/daily/list'),
});

const periodicQuery = useQuery({
  queryKey: ['reports-periodic'],
  queryFn: () => apiClient.get<PeriodicReportPayload>('/api/v1/reports/periodic'),
});

const dailyQuery = useQuery({
  queryKey: ['report-daily', reportDate],
  queryFn: () => apiClient.get<DailyReportPayload>(`/api/v1/reports/daily?date=${reportDate.value}`),
});

const bundleQuery = useQuery({
  queryKey: ['report-bundle', reportDate],
  queryFn: () => apiClient.get<BundlePayload>(`/api/v1/reports/daily/bundle?date=${reportDate.value}`),
});

const compareQuery = useQuery({
  queryKey: ['report-compare', compareDate, baselineDate],
  queryFn: () => apiClient.get<ComparePayload>(`/api/v1/reports/daily/compare?current_date=${compareDate.value}&baseline_date=${baselineDate.value}`),
});

const generateDailyMutation = useMutation({
  mutationFn: () => apiClient.post('/api/v1/reports/daily/generate', { trade_date: reportDate.value }),
  onSuccess: async () => {
    feedback.value = '日报已生成并回填到列表。';
    pageError.value = '';
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['report-daily'] }),
      queryClient.invalidateQueries({ queryKey: ['reports-daily-list'] }),
      queryClient.invalidateQueries({ queryKey: ['reports-history'] }),
    ]);
  },
  onError: (error) => {
    pageError.value = error instanceof Error ? error.message : '生成日报失败';
  },
});

const generateBundleMutation = useMutation({
  mutationFn: () => apiClient.post('/api/v1/reports/daily/bundle/generate', { trade_date: reportDate.value }),
  onSuccess: async () => {
    feedback.value = 'Bundle 已生成。';
    pageError.value = '';
    await queryClient.invalidateQueries({ queryKey: ['report-bundle'] });
  },
  onError: (error) => {
    pageError.value = error instanceof Error ? error.message : '生成 Bundle 失败';
  },
});

function asRecord(value: unknown): LooseRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as LooseRecord : {};
}

function asList(value: unknown): LooseRecord[] {
  return Array.isArray(value) ? value.filter((item): item is LooseRecord => Boolean(item) && typeof item === 'object' && !Array.isArray(item)) : [];
}

function displayValue(value: unknown): string {
  if (value == null) {
    return '--';
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

function toStats(value: unknown, limit = 6): Array<{ label: string; value: string }> {
  return Object.entries(asRecord(value))
    .slice(0, limit)
    .map(([label, raw]) => ({ label, value: displayValue(raw) }));
}

const history = computed(() => historyQuery.data.value ?? null);
const dailyStats = computed(() => history.value?.daily_stats ?? []);
const historySignals = computed(() => history.value?.signals ?? []);
const reportCount = computed(() => listQuery.data.value?.items?.length ?? 0);
const dailyReportBody = computed(() => {
  const report = dailyQuery.data.value?.report;
  const record = asRecord(report);
  return asRecord(record.content_json ?? record);
});
const bundleBody = computed(() => {
  const bundle = bundleQuery.data.value?.bundle;
  const record = asRecord(bundle);
  return asRecord(record.content_json ?? record);
});
const periodicReportBody = computed(() => asRecord(periodicQuery.data.value?.report));
const periodicItems = computed(() => asList((periodicQuery.data.value as LooseRecord)?.items));
const compareBody = computed(() => asRecord(compareQuery.data.value?.comparison));
</script>

<template>
  <PageHeader title="报告中心" subtitle="历史统计、日报、Bundle、差异对比与周期报告都在这里完成。" />

  <div class="mb-6 grid gap-4 md:grid-cols-4">
    <MetricCard label="历史交易日" :value="String(dailyStats.length)" helper="历史统计返回的有效日期数" tone="brand" />
    <MetricCard label="历史信号" :value="String(historySignals.length)" helper="用于复盘和筛查的历史信号数" :tone="historySignals.length ? 'positive' : 'default'" />
    <MetricCard label="日报索引" :value="String(reportCount)" helper="最近可直接查看的日报文件条目" />
    <MetricCard label="当前日期" :value="reportDate" helper="生成日报与 bundle 时采用的日期" />
  </div>

  <div v-if="pageError" class="mb-4">
    <ErrorPanel :message="pageError" />
  </div>
  <div v-else-if="feedback" class="mb-4 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
    {{ feedback }}
  </div>

  <div class="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
    <AppCard title="历史统计" subtitle="按日期聚合胜率、总单数，并保留历史信号表做快速复盘。">
      <div v-if="historyQuery.isLoading.value"><LoadingSkeleton :lines="8" height="18px" /></div>
      <template v-else>
        <div v-if="dailyStats.length" class="grid gap-3 md:grid-cols-2">
          <div v-for="item in dailyStats.slice(0, 8)" :key="String(item.date)" class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
            <div class="flex items-center justify-between gap-3">
              <div class="text-sm font-semibold text-white">{{ String(item.date || '--') }}</div>
              <StateBadge :label="`胜率 ${String(item.win_rate ?? '--')}%`" tone="brand" />
            </div>
            <div class="mt-3 text-sm text-slate-300">总单 {{ String(item.total ?? '--') }} · 成功 {{ String(item.success ?? '--') }} · 失败 {{ String(item.fail ?? '--') }}</div>
          </div>
        </div>
        <EmptyPanel v-else title="暂无历史统计" description="当前还没有可复盘的日报统计结果。" />

        <div class="mt-5 overflow-x-auto" v-if="historySignals.length">
          <table class="panel-table">
            <thead>
              <tr>
                <th>日期</th>
                <th>时间</th>
                <th>股票</th>
                <th>方向</th>
                <th>状态</th>
                <th>描述</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in historySignals.slice(0, 12)" :key="String(item.id || `${item.date}-${item.time}-${item.code}`)">
                <td>{{ String(item.date || '--') }}</td>
                <td>{{ String(item.time || '--') }}</td>
                <td>{{ String(item.name || item.code || '--') }}</td>
                <td>{{ String(item.type || item.side || '--') }}</td>
                <td>{{ String(item.status || '--') }}</td>
                <td class="max-w-[320px] text-slate-400">{{ String(item.desc || item.description || '--') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </AppCard>

    <AppCard title="日报 / Bundle / 对比" subtitle="围绕单个交易日生成报告，并和基准日做结构化对比。">
      <div class="grid gap-3 md:grid-cols-3">
        <input v-model="reportDate" type="date" class="input-base" />
        <button class="btn-primary" @click="generateDailyMutation.mutate()">生成日报</button>
        <button class="btn-secondary" @click="generateBundleMutation.mutate()">生成 Bundle</button>
      </div>

      <div class="mt-4 grid gap-4 xl:grid-cols-2">
        <div class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          <div class="flex items-center justify-between gap-3">
            <div class="text-sm font-semibold text-white">日报详情</div>
            <StateBadge :label="dailyQuery.data.value?.source || 'unknown'" tone="brand" />
          </div>
          <div class="mt-4" v-if="dailyQuery.isLoading.value"><LoadingSkeleton :lines="6" height="18px" /></div>
          <MiniStatList v-else-if="toStats(dailyReportBody).length" :items="toStats(dailyReportBody, 8)" />
          <EmptyPanel v-else title="暂无日报内容" description="请先生成日报，或切换到已有结果的日期。" />
        </div>

        <div class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          <div class="flex items-center justify-between gap-3">
            <div class="text-sm font-semibold text-white">Bundle 内容</div>
            <StateBadge :label="bundleQuery.data.value?.source || 'unknown'" tone="default" />
          </div>
          <div class="mt-4" v-if="bundleQuery.isLoading.value"><LoadingSkeleton :lines="6" height="18px" /></div>
          <MiniStatList v-else-if="toStats(bundleBody).length" :items="toStats(bundleBody, 8)" />
          <EmptyPanel v-else title="暂无 Bundle" description="Bundle 会在生成后展示重点摘要与聚合结果。" />
        </div>
      </div>

      <div class="mt-6 grid gap-3 md:grid-cols-3">
        <input v-model="compareDate" type="date" class="input-base" />
        <input v-model="baselineDate" type="date" class="input-base" />
        <button class="btn-secondary" @click="compareQuery.refetch()">刷新差异对比</button>
      </div>
      <div class="mt-4 rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
        <div class="flex items-center justify-between gap-3">
          <div class="text-sm font-semibold text-white">日报差异</div>
          <StateBadge :label="`${compareDate} vs ${baselineDate}`" tone="warning" />
        </div>
        <div class="mt-4" v-if="compareQuery.isLoading.value"><LoadingSkeleton :lines="6" height="18px" /></div>
        <MiniStatList v-else-if="toStats(compareBody).length" :items="toStats(compareBody, 10)" />
        <EmptyPanel v-else title="暂无对比结果" description="请确认两天都存在日报，或重新选择日期。" />
      </div>
    </AppCard>
  </div>

  <div class="mt-6 grid gap-4 xl:grid-cols-[0.85fr_1.15fr]">
    <AppCard title="日报列表" subtitle="最近生成的日报索引，可快速确认已有报告范围。">
      <div v-if="listQuery.isLoading.value"><LoadingSkeleton :lines="6" height="18px" /></div>
      <div v-else-if="(listQuery.data.value?.items || []).length" class="space-y-3">
        <div v-for="item in listQuery.data.value?.items" :key="String(item.id || item.date || item.trade_date)" class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          <div class="flex items-center justify-between gap-3">
            <div>
              <div class="text-sm font-semibold text-white">{{ item.title || item.date || item.trade_date || '--' }}</div>
              <div class="mt-1 text-sm text-slate-400">日期 {{ formatDate(String(item.date || item.trade_date || '')) }}</div>
            </div>
            <StateBadge :label="item.exists_md ? '含 Markdown' : 'JSON 结果'" :tone="item.exists_md ? 'positive' : 'default'" />
          </div>
        </div>
      </div>
      <EmptyPanel v-else title="暂无日报索引" description="生成过日报后，这里会显示最近的可用记录。" />
    </AppCard>

    <AppCard title="周期报告" subtitle="兼容 legacy 周期报告与 next 周期记录，两种结果都可结构化展示。">
      <div v-if="periodicQuery.isLoading.value"><LoadingSkeleton :lines="6" height="18px" /></div>
      <div v-else-if="toStats(periodicReportBody).length" class="space-y-4">
        <MiniStatList :items="toStats(periodicReportBody, 10)" />
      </div>
      <div v-else-if="periodicItems.length" class="overflow-x-auto">
        <table class="panel-table">
          <thead>
            <tr>
              <th>类型</th>
              <th>周期键</th>
              <th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in periodicItems" :key="String(item.id || item.period_key || index)">
              <td>{{ String(item.period_kind || '--') }}</td>
              <td>{{ String(item.period_key || '--') }}</td>
              <td>{{ formatDateTime(String(item.created_at || '')) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <EmptyPanel v-else title="暂无周期报告" description="周报或月报生成后会在这里集中展示。" />
    </AppCard>
  </div>
</template>
