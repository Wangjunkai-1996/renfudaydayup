<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query';
import { computed } from 'vue';

import { apiClient } from '@/shared/api/client';
import type { DashboardSummary, DiagnosticsOverview } from '@/shared/api/types';
import { formatMoney } from '@/shared/lib/format';
import AppCard from '@/shared/ui/AppCard.vue';
import PageHeader from '@/shared/ui/PageHeader.vue';
import PulseChart from '@/shared/ui/PulseChart.vue';
import StatCard from '@/shared/ui/StatCard.vue';
import { useRealtimeStore } from '@/shared/stores/realtime';

const summaryQuery = useQuery({
  queryKey: ['dashboard-summary'],
  queryFn: () => apiClient.get<DashboardSummary>('/api/v1/dashboard/summary'),
});

const diagnosticsQuery = useQuery({
  queryKey: ['dashboard-diagnostics'],
  queryFn: () => apiClient.get<DiagnosticsOverview>('/api/v1/dashboard/diagnostics-overview'),
});

const summary = computed<DashboardSummary>(() => summaryQuery.data.value ?? {
  user: { id: '', username: '', role: 'user', is_active: false, created_at: '', updated_at: '' },
  pulse: [],
  watchlist_count: 0,
  signal_counts: {},
  paper_summary: { starting_cash: 0, cash: 0, realized_pnl: 0 },
  alerts: [],
});

const diagnostics = computed<DiagnosticsOverview>(() => diagnosticsQuery.data.value ?? {
  preflight: {},
  focus_guard: {},
  rejection_monitor: {},
  focus_review: {},
});

const totalSignals = computed(() => Object.values(summary.value.signal_counts).reduce((sum, value) => sum + Number(value), 0));
const realtimeStore = useRealtimeStore();
const pulseItems = computed(() => (realtimeStore.hasPulse ? realtimeStore.pulse : summary.value.pulse));
</script>

<template>
  <PageHeader title="Dashboard" subtitle="桌面优先的新首页：市场脉搏、用户摘要、诊断概览和实时入口。" />

  <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
    <StatCard label="自选股数量" :value="String(summary.watchlist_count)" tone="brand" />
    <StatCard label="信号总计" :value="String(totalSignals)" />
    <StatCard label="模拟现金" :value="formatMoney(summary.paper_summary.cash)" tone="positive" />
    <StatCard label="累计盈亏" :value="formatMoney(summary.paper_summary.realized_pnl)" :tone="summary.paper_summary.realized_pnl >= 0 ? 'positive' : 'negative'" />
  </div>

  <div class="mt-6 grid gap-4 xl:grid-cols-[1.25fr_1fr]">
    <AppCard title="MarketPulseBar" subtitle="共享行情引擎输出的全局市场脉搏。">
      <PulseChart :items="pulseItems" />
    </AppCard>

    <AppCard title="Global Alerts" subtitle="新栈上线提醒与系统消息。">
      <div class="mb-3 text-xs text-slate-500">实时流：{{ realtimeStore.connected ? '在线' : '离线' }}<span v-if="realtimeStore.lastEventAt"> · 最近事件 {{ realtimeStore.lastEventAt }}</span></div>
      <div class="space-y-3">
        <div v-for="alert in summary.alerts" :key="alert.title" class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          <div class="text-sm font-medium text-white">{{ alert.title }}</div>
          <div class="mt-1 text-sm text-slate-400">{{ alert.message }}</div>
        </div>
      </div>
    </AppCard>
  </div>

  <div class="mt-6 grid gap-4 xl:grid-cols-3">
    <AppCard title="Preflight" subtitle="策略健康和运行前检查。">
      <pre class="overflow-auto text-xs text-slate-300">{{ JSON.stringify(diagnostics.preflight, null, 2) }}</pre>
    </AppCard>
    <AppCard title="Focus Guard" subtitle="焦点放行/防守摘要。">
      <pre class="overflow-auto text-xs text-slate-300">{{ JSON.stringify(diagnostics.focus_guard, null, 2) }}</pre>
    </AppCard>
    <AppCard title="Review & Rejection" subtitle="复盘与拒绝画像。">
      <pre class="overflow-auto text-xs text-slate-300">{{ JSON.stringify({ review: diagnostics.focus_review, rejection: diagnostics.rejection_monitor }, null, 2) }}</pre>
    </AppCard>
  </div>
</template>
