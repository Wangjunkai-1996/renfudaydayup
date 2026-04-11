<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query';
import { computed } from 'vue';
import { RouterLink } from 'vue-router';

import { apiClient } from '@/shared/api/client';
import type { DashboardSummary, DiagnosticsOverview, MarketWorkbenchPayload, SignalItem } from '@/shared/api/types';
import { formatMoney, formatPercent } from '@/shared/lib/format';
import { useRealtimeStore } from '@/shared/stores/realtime';
import AppCard from '@/shared/ui/AppCard.vue';
import EmptyPanel from '@/shared/ui/EmptyPanel.vue';
import ErrorPanel from '@/shared/ui/ErrorPanel.vue';
import LoadingSkeleton from '@/shared/ui/LoadingSkeleton.vue';
import MetricCard from '@/shared/ui/MetricCard.vue';
import PageHeader from '@/shared/ui/PageHeader.vue';
import PulseChart from '@/shared/ui/PulseChart.vue';
import SignalListItem from '@/shared/ui/SignalListItem.vue';
import StateBadge from '@/shared/ui/StateBadge.vue';
import WorkbenchChart from '@/shared/ui/WorkbenchChart.vue';

const realtimeStore = useRealtimeStore();

const summaryQuery = useQuery({
  queryKey: ['dashboard-summary'],
  queryFn: () => apiClient.get<DashboardSummary>('/api/v1/dashboard/summary'),
});

const diagnosticsQuery = useQuery({
  queryKey: ['dashboard-diagnostics'],
  queryFn: () => apiClient.get<DiagnosticsOverview>('/api/v1/dashboard/diagnostics-overview'),
});

const signalsQuery = useQuery({
  queryKey: ['dashboard-signals'],
  queryFn: () => apiClient.get<SignalItem[]>('/api/v1/signals?limit=8'),
});

const workbenchQuery = useQuery({
  queryKey: ['dashboard-workbench'],
  queryFn: () => apiClient.get<MarketWorkbenchPayload>('/api/v1/market/workbench'),
});

const summary = computed<DashboardSummary | null>(() => summaryQuery.data.value ?? null);
const diagnostics = computed<DiagnosticsOverview | null>(() => diagnosticsQuery.data.value ?? realtimeStore.diagnostics ?? null);
const workbench = computed<MarketWorkbenchPayload | null>(() => workbenchQuery.data.value ?? summary.value?.workbench ?? null);
const focusItem = computed(() => workbench.value?.items?.[0] ?? null);
const pulseItems = computed(() => (realtimeStore.hasPulse ? realtimeStore.pulse : summary.value?.pulse ?? []));
const signals = computed(() => (realtimeStore.hasSignals ? realtimeStore.signals.slice(0, 8) : signalsQuery.data.value ?? []));
const totalSignals = computed(() => Object.values(summary.value?.signal_counts ?? {}).reduce((sum, value) => sum + Number(value), 0));

const summaryError = computed(() => summaryQuery.error.value instanceof Error ? summaryQuery.error.value.message : 'Dashboard 加载失败');
const diagnosticsError = computed(() => diagnosticsQuery.error.value instanceof Error ? diagnosticsQuery.error.value.message : '诊断概览加载失败');
</script>

<template>
  <PageHeader title="总览" subtitle="桌面优先的新首页：市场脉搏、真实工作区预览、用户摘要与诊断总览。">
    <div class="flex flex-wrap gap-2">
      <StateBadge :label="realtimeStore.connected ? '实时已连接' : '实时未连接'" :tone="realtimeStore.connected ? 'positive' : 'warning'" />
      <StateBadge :label="realtimeStore.legacyMode ? 'Legacy 真数据' : 'Next 用户隔离'" tone="brand" />
    </div>
  </PageHeader>

  <div v-if="summaryQuery.isLoading.value" class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
    <div v-for="index in 4" :key="index" class="glass-card p-5"><LoadingSkeleton :lines="2" height="22px" /></div>
  </div>
  <ErrorPanel v-else-if="summaryQuery.isError.value" :message="summaryError" />
  <div v-else class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
    <MetricCard label="自选数量" :value="String(summary?.watchlist_count ?? 0)" helper="当前登录用户的自选池规模" tone="brand" />
    <MetricCard label="信号总量" :value="String(totalSignals)" helper="按状态聚合的历史信号总量" />
    <MetricCard label="账户现金" :value="formatMoney(summary?.paper_summary.cash ?? 0)" helper="模拟账户可用现金" tone="positive" />
    <MetricCard label="累计盈亏" :value="formatMoney(summary?.paper_summary.realized_pnl ?? 0)" :helper="`净值 ${formatMoney(summary?.paper_summary.nav ?? 0)}`" :tone="(summary?.paper_summary.realized_pnl ?? 0) >= 0 ? 'positive' : 'negative'" />
  </div>

  <div class="mt-6 grid gap-4 xl:grid-cols-[0.95fr_1.35fr_0.9fr]">
    <AppCard title="市场脉搏" subtitle="共享市场状态和活跃标的涨跌分布。">
      <template #action>
        <RouterLink to="/market" class="btn-secondary">进入工作区</RouterLink>
      </template>
      <PulseChart v-if="pulseItems.length" :items="pulseItems" />
      <EmptyPanel v-else title="暂无市场脉搏" description="等待行情快照或工作区数据同步。" />
    </AppCard>

    <AppCard title="焦点工作区预览" subtitle="旧首页 charts-wrapper 的核心能力已迁到这里。">
      <template #action>
        <RouterLink to="/market" class="btn-primary">打开完整工作区</RouterLink>
      </template>
      <div v-if="focusItem" class="space-y-4">
        <div class="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          <div>
            <div class="text-lg font-semibold text-white">{{ focusItem.name }} · {{ focusItem.symbol }}</div>
            <div class="mt-1 text-sm text-slate-400">{{ focusItem.context.trend || '趋势上下文准备中' }}</div>
          </div>
          <div class="text-right">
            <div class="text-2xl font-semibold text-white">{{ focusItem.market.last_price.toFixed(2) }}</div>
            <div :class="focusItem.market.change_pct >= 0 ? 'text-emerald-300' : 'text-rose-300'">{{ formatPercent(focusItem.market.change_pct) }}</div>
          </div>
        </div>
        <WorkbenchChart :name="focusItem.name" :points="focusItem.series" :annotations="focusItem.annotations" />
      </div>
      <EmptyPanel v-else title="暂无工作区数据" description="请先在自选管理中添加股票，或等待 Legacy 工作区同步。" />
    </AppCard>

    <AppCard title="实时信号流" subtitle="用户私有信号、状态变化和快速详情入口。">
      <template #action>
        <RouterLink to="/signals" class="btn-secondary">查看全部</RouterLink>
      </template>
      <div v-if="signalsQuery.isLoading.value && !signals.length"><LoadingSkeleton :lines="4" height="72px" /></div>
      <div v-else-if="signals.length" class="space-y-3">
        <SignalListItem v-for="item in signals" :key="item.id" :item="item" compact />
      </div>
      <EmptyPanel v-else title="暂无实时信号" description="当前没有待处理或最新生成的信号。" />
    </AppCard>
  </div>

  <div class="mt-6 grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
    <AppCard title="诊断总览" subtitle="Preflight、焦点防守、拒绝画像与回顾摘要。">
      <div v-if="diagnosticsQuery.isLoading.value && !diagnostics"><LoadingSkeleton :lines="6" height="18px" /></div>
      <ErrorPanel v-else-if="diagnosticsQuery.isError.value && !diagnostics" :message="diagnosticsError" />
      <div v-else-if="diagnostics" class="grid gap-4 md:grid-cols-2">
        <div class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          <div class="text-sm font-semibold text-white">{{ diagnostics.preflight.headline || 'Preflight' }}</div>
          <div class="mt-2 text-sm text-slate-400">{{ (diagnostics.preflight.details?.message as string) || '已接入真实预检结果。' }}</div>
        </div>
        <div class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          <div class="text-sm font-semibold text-white">{{ diagnostics.focus_guard.headline || '焦点防守' }}</div>
          <div class="mt-2 text-sm text-slate-400">{{ diagnostics.focus_guard.summary || '已接入焦点股放行/防守摘要。' }}</div>
        </div>
        <div class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          <div class="text-sm font-semibold text-white">{{ diagnostics.rejection_monitor.headline || '拒绝画像' }}</div>
          <ul class="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-400">
            <li v-for="hint in diagnostics.rejection_monitor.slot_hints || []" :key="hint">{{ hint }}</li>
            <li v-if="!(diagnostics.rejection_monitor.slot_hints || []).length">暂无额外拒绝提示</li>
          </ul>
        </div>
        <div class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          <div class="text-sm font-semibold text-white">{{ diagnostics.focus_review.headline || '回顾摘要' }}</div>
          <div class="mt-2 text-sm text-slate-400">成功 {{ diagnostics.focus_review.success_count ?? '--' }} · 失败 {{ diagnostics.focus_review.fail_count ?? '--' }}</div>
        </div>
      </div>
    </AppCard>

    <AppCard title="快捷入口" subtitle="日报、调参、诊断和工作区的高频操作入口。">
      <div class="grid gap-3">
        <RouterLink to="/reports" class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4 transition hover:border-slate-700 hover:bg-slate-900/80">
          <div class="font-medium text-white">报告中心</div>
          <div class="mt-1 text-sm text-slate-400">查看历史统计、日报、bundle 和对比结果。</div>
        </RouterLink>
        <RouterLink to="/diagnostics" class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4 transition hover:border-slate-700 hover:bg-slate-900/80">
          <div class="font-medium text-white">诊断调优</div>
          <div class="mt-1 text-sm text-slate-400">查看 preflight、时段表现、edge diagnostics 与 tuning 建议。</div>
        </RouterLink>
        <RouterLink to="/strategy" class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4 transition hover:border-slate-700 hover:bg-slate-900/80">
          <div class="font-medium text-white">策略参数</div>
          <div class="mt-1 text-sm text-slate-400">维护风控参数、时段模板和个股特化设置。</div>
        </RouterLink>
      </div>
    </AppCard>
  </div>
</template>
