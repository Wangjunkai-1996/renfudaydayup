<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query';
import { computed, ref } from 'vue';

import { apiClient } from '@/shared/api/client';
import type { SignalExplainPayload, SignalItem } from '@/shared/api/types';
import { formatDateTime, formatNumber } from '@/shared/lib/format';
import { useRealtimeStore } from '@/shared/stores/realtime';
import AppCard from '@/shared/ui/AppCard.vue';
import DrawerShell from '@/shared/ui/DrawerShell.vue';
import EmptyPanel from '@/shared/ui/EmptyPanel.vue';
import LoadingSkeleton from '@/shared/ui/LoadingSkeleton.vue';
import PageHeader from '@/shared/ui/PageHeader.vue';
import SignalListItem from '@/shared/ui/SignalListItem.vue';
import StateBadge from '@/shared/ui/StateBadge.vue';
import WorkbenchChart from '@/shared/ui/WorkbenchChart.vue';

const realtimeStore = useRealtimeStore();
const selectedSignalId = ref('');
const statusFilter = ref('');
const sideFilter = ref('');
const keyword = ref('');

const signalsQuery = useQuery({ queryKey: ['signals'], queryFn: () => apiClient.get<SignalItem[]>('/api/v1/signals?limit=120') });

const detailQuery = useQuery({
  queryKey: ['signal-detail', selectedSignalId],
  enabled: computed(() => Boolean(selectedSignalId.value)),
  queryFn: () => apiClient.get<SignalItem>(`/api/v1/signals/${selectedSignalId.value}`),
});

const explainQuery = useQuery({
  queryKey: ['signal-explain', selectedSignalId],
  enabled: computed(() => Boolean(selectedSignalId.value)),
  queryFn: () => apiClient.get<SignalExplainPayload>(`/api/v1/signals/${selectedSignalId.value}/explain`),
});

const sourceSignals = computed(() => (realtimeStore.hasSignals ? realtimeStore.signals : signalsQuery.data.value ?? []));
const signals = computed(() => sourceSignals.value.filter((item) => {
  if (statusFilter.value && item.status !== statusFilter.value) {
    return false;
  }
  if (sideFilter.value && item.side !== sideFilter.value) {
    return false;
  }
  if (keyword.value.trim()) {
    const token = keyword.value.trim().toLowerCase();
    return item.symbol.toLowerCase().includes(token) || item.name.toLowerCase().includes(token) || item.description.toLowerCase().includes(token);
  }
  return true;
}));
</script>

<template>
  <PageHeader title="信号中心" subtitle="实时信号流、过滤器、详情抽屉和 explain 入口。">
    <div class="flex flex-wrap gap-2">
      <StateBadge :label="realtimeStore.connected ? '实时流在线' : '实时流离线'" :tone="realtimeStore.connected ? 'positive' : 'warning'" />
      <StateBadge :label="signals.length ? `筛选结果 ${signals.length}` : '暂无命中信号'" :tone="signals.length ? 'brand' : 'default'" />
    </div>
  </PageHeader>

  <AppCard title="筛选条件" subtitle="按状态、方向和关键字过滤实时信号。">
    <div class="grid gap-3 md:grid-cols-4">
      <select v-model="statusFilter" class="input-base">
        <option value="">全部状态</option>
        <option value="pending">待处理</option>
        <option value="success">成功</option>
        <option value="fail">失败</option>
        <option value="flat">平仓</option>
      </select>
      <select v-model="sideFilter" class="input-base">
        <option value="">全部方向</option>
        <option value="BUY">买入</option>
        <option value="SELL">卖出</option>
      </select>
      <input v-model="keyword" class="input-base" placeholder="搜索代码 / 名称 / 描述" />
      <button class="btn-secondary" @click="statusFilter = ''; sideFilter = ''; keyword = ''">重置筛选</button>
    </div>
  </AppCard>

  <AppCard class="mt-6" title="实时信号列表" subtitle="点击任意信号，右侧抽屉查看详情、图表和解释。">
    <div v-if="signalsQuery.isLoading.value && !signals.length"><LoadingSkeleton :lines="5" height="80px" /></div>
    <div v-else-if="signals.length" class="space-y-3">
      <button v-for="item in signals" :key="item.id" class="block w-full text-left" @click="selectedSignalId = item.id">
        <SignalListItem :item="item" />
      </button>
    </div>
    <EmptyPanel v-else title="暂无信号" description="当前筛选条件下没有可展示的信号。" />
  </AppCard>

  <DrawerShell :open="Boolean(selectedSignalId)" title="信号详情" subtitle="信号生命周期、解释和局部图表窗口。" @close="selectedSignalId = ''">
    <div v-if="detailQuery.isLoading.value || explainQuery.isLoading.value"><LoadingSkeleton :lines="8" height="20px" /></div>
    <div v-else-if="detailQuery.data.value" class="space-y-5">
      <div class="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
        <div class="flex items-start justify-between gap-4">
          <div>
            <div class="text-lg font-semibold text-white">{{ detailQuery.data.value.name }} · {{ detailQuery.data.value.symbol }}</div>
            <div class="mt-2 text-sm text-slate-400">{{ detailQuery.data.value.description }}</div>
          </div>
          <div class="text-right">
            <StateBadge :label="detailQuery.data.value.side" :tone="detailQuery.data.value.side === 'BUY' ? 'positive' : 'negative'" />
            <div class="mt-2 text-sm text-slate-400">{{ detailQuery.data.value.status }}</div>
          </div>
        </div>
        <div class="mt-4 grid gap-3 md:grid-cols-3">
          <div class="rounded-2xl border border-slate-800 bg-slate-950/60 p-3">
            <div class="text-xs text-slate-500">价格</div>
            <div class="mt-2 text-lg text-white">{{ formatNumber(detailQuery.data.value.price) }}</div>
          </div>
          <div class="rounded-2xl border border-slate-800 bg-slate-950/60 p-3">
            <div class="text-xs text-slate-500">触发时间</div>
            <div class="mt-2 text-lg text-white">{{ formatDateTime(detailQuery.data.value.occurred_at) }}</div>
          </div>
          <div class="rounded-2xl border border-slate-800 bg-slate-950/60 p-3">
            <div class="text-xs text-slate-500">级别</div>
            <div class="mt-2 text-lg text-white">{{ detailQuery.data.value.level }}</div>
          </div>
        </div>
      </div>

      <div v-if="explainQuery.data.value?.explain?.chart_points?.length" class="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
        <div class="mb-3 text-sm font-semibold text-white">局部图表窗口</div>
        <WorkbenchChart :name="detailQuery.data.value.name" :points="explainQuery.data.value.explain.chart_points || []" />
      </div>

      <div class="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
        <div class="text-sm font-semibold text-white">Explain 摘要</div>
        <div class="mt-3 text-sm text-slate-300">{{ explainQuery.data.value?.explain?.summary || '该信号已接入 explain，但当前没有额外摘要。' }}</div>
        <ul class="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-400">
          <li v-for="insight in explainQuery.data.value?.explain?.insights || []" :key="insight">{{ insight }}</li>
          <li v-if="!(explainQuery.data.value?.explain?.insights || []).length">暂无额外 insight。</li>
        </ul>
      </div>

      <div class="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
        <div class="text-sm font-semibold text-white">关键因子</div>
        <div class="mt-3 flex flex-wrap gap-2">
          <StateBadge v-for="factor in (explainQuery.data.value?.explain?.factors || []).map((item) => String(item))" :key="factor" :label="factor" tone="brand" />
          <span v-if="!(explainQuery.data.value?.explain?.factors || []).length" class="text-sm text-slate-500">暂无结构化因子。</span>
        </div>
      </div>
    </div>
    <EmptyPanel v-else title="未选择信号" description="从左侧列表中点击一条信号以查看详情。" />
  </DrawerShell>
</template>
