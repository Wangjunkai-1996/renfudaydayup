<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query';
import { computed, ref, watch } from 'vue';

import { apiClient } from '@/shared/api/client';
import type { MarketPulseItem, MarketWorkbenchPayload, WatchlistItem } from '@/shared/api/types';
import { formatPercent } from '@/shared/lib/format';
import { useRealtimeStore } from '@/shared/stores/realtime';
import AppCard from '@/shared/ui/AppCard.vue';
import EmptyPanel from '@/shared/ui/EmptyPanel.vue';
import LoadingSkeleton from '@/shared/ui/LoadingSkeleton.vue';
import PageHeader from '@/shared/ui/PageHeader.vue';
import PulseChart from '@/shared/ui/PulseChart.vue';
import StateBadge from '@/shared/ui/StateBadge.vue';
import WorkbenchChart from '@/shared/ui/WorkbenchChart.vue';

const queryClient = useQueryClient();
const realtimeStore = useRealtimeStore();
const selectedSymbol = ref('');

const workbenchQuery = useQuery({
  queryKey: ['market-workbench'],
  queryFn: () => apiClient.get<MarketWorkbenchPayload>('/api/v1/market/workbench'),
});

const watchlistQuery = useQuery({
  queryKey: ['market-watchlist'],
  queryFn: () => apiClient.get<WatchlistItem[]>('/api/v1/market/watchlist'),
});

const pulseQuery = useQuery({
  queryKey: ['market-pulse'],
  queryFn: () => apiClient.get<MarketPulseItem[]>('/api/v1/market/pulse'),
});

const reorderMutation = useMutation({
  mutationFn: (symbols: string[]) => apiClient.post<{ success: boolean }>('/api/v1/watchlist/reorder', { symbols }),
  onSuccess: async () => {
    await queryClient.invalidateQueries({ queryKey: ['market-watchlist'] });
    await queryClient.invalidateQueries({ queryKey: ['market-workbench'] });
  },
});

const workbench = computed(() => workbenchQuery.data.value ?? null);
const watchlistItems = computed(() => watchlistQuery.data.value ?? []);
const pulseItems = computed(() => (realtimeStore.hasPulse ? realtimeStore.pulse : pulseQuery.data.value ?? []));
const workbenchItems = computed(() => workbench.value?.items ?? []);
const currentItem = computed(() => workbenchItems.value.find((item) => item.symbol === selectedSymbol.value) ?? workbenchItems.value[0] ?? null);

watch(
  () => workbench.value?.active_symbol,
  (activeSymbol) => {
    if (!selectedSymbol.value && activeSymbol) {
      selectedSymbol.value = activeSymbol;
    }
    if (selectedSymbol.value && !workbenchItems.value.some((item) => item.symbol === selectedSymbol.value)) {
      selectedSymbol.value = activeSymbol || workbenchItems.value[0]?.symbol || '';
    }
  },
  { immediate: true },
);

function moveSymbol(symbol: string, direction: -1 | 1) {
  const next = [...watchlistItems.value].sort((left, right) => left.sort_order - right.sort_order);
  const index = next.findIndex((item) => item.symbol === symbol);
  const targetIndex = index + direction;
  if (index < 0 || targetIndex < 0 || targetIndex >= next.length) {
    return;
  }
  const clone = [...next];
  const [item] = clone.splice(index, 1);
  clone.splice(targetIndex, 0, item);
  reorderMutation.mutate(clone.map((row) => row.symbol));
}
</script>

<template>
  <PageHeader title="盯盘工作区" subtitle="多股票分时图、自选切换、上下文与报价联动。">
    <div class="flex flex-wrap gap-2">
      <StateBadge :label="workbench?.source === 'legacy' ? 'Legacy 工作区' : 'Next 工作区'" tone="brand" />
      <StateBadge :label="currentItem ? `当前 ${currentItem.name}` : '等待选择标的'" :tone="currentItem ? 'positive' : 'warning'" />
    </div>
  </PageHeader>

  <div class="grid gap-4 xl:grid-cols-[1.25fr_0.75fr]">
    <AppCard title="多股票工作区" subtitle="顶部 tabs 切股，主图区展示分时、VWAP 和参考线。">
      <div v-if="workbenchQuery.isLoading.value"><LoadingSkeleton :lines="5" height="20px" /></div>
      <template v-else-if="currentItem">
        <div class="mb-4 flex flex-wrap gap-2">
          <button
            v-for="item in workbenchItems"
            :key="item.symbol"
            class="rounded-2xl px-4 py-2 text-sm font-medium transition"
            :class="selectedSymbol === item.symbol ? 'bg-indigo-500/20 text-indigo-100' : 'border border-slate-700 bg-slate-900/60 text-slate-300 hover:bg-slate-800'"
            @click="selectedSymbol = item.symbol"
          >
            {{ item.name }}
          </button>
        </div>
        <div class="mb-4 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          <div>
            <div class="text-xl font-semibold text-white">{{ currentItem.name }} · {{ currentItem.symbol }}</div>
            <div class="mt-1 text-sm text-slate-400">{{ currentItem.context.trend || '趋势上下文待补充' }}</div>
          </div>
          <div class="text-right">
            <div class="text-3xl font-semibold text-white">{{ currentItem.market.last_price.toFixed(2) }}</div>
            <div :class="currentItem.market.change_pct >= 0 ? 'text-emerald-300' : 'text-rose-300'">{{ formatPercent(currentItem.market.change_pct) }}</div>
          </div>
        </div>
        <WorkbenchChart :name="currentItem.name" :points="currentItem.series" :annotations="currentItem.annotations" />
        <div class="mt-4 grid gap-4 xl:grid-cols-[1fr_0.95fr]">
          <div class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
            <div class="text-sm font-semibold text-white">行情摘要</div>
            <div class="mt-3 grid gap-3 md:grid-cols-2">
              <div class="rounded-2xl border border-slate-800 bg-slate-900/60 p-3">
                <div class="text-xs text-slate-500">VWAP</div>
                <div class="mt-2 text-lg text-white">{{ currentItem.market.vwap?.toFixed(2) || '--' }}</div>
              </div>
              <div class="rounded-2xl border border-slate-800 bg-slate-900/60 p-3">
                <div class="text-xs text-slate-500">昨收</div>
                <div class="mt-2 text-lg text-white">{{ currentItem.market.prev_close?.toFixed(2) || '--' }}</div>
              </div>
              <div class="rounded-2xl border border-slate-800 bg-slate-900/60 p-3">
                <div class="text-xs text-slate-500">开盘价</div>
                <div class="mt-2 text-lg text-white">{{ currentItem.market.open_price?.toFixed(2) || '--' }}</div>
              </div>
              <div class="rounded-2xl border border-slate-800 bg-slate-900/60 p-3">
                <div class="text-xs text-slate-500">更新时间</div>
                <div class="mt-2 text-lg text-white">{{ currentItem.market.updated_at || '--' }}</div>
              </div>
            </div>
          </div>
          <div class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
            <div class="text-sm font-semibold text-white">上下文 / 新闻</div>
            <div class="mt-3 text-sm text-slate-400">行业：{{ currentItem.context.industry || '未知' }}</div>
            <div class="mt-3 space-y-3">
              <div v-for="news in currentItem.context.news" :key="`${news.title}-${news.time}`" class="rounded-2xl border border-slate-800 bg-slate-900/60 p-3">
                <div class="font-medium text-slate-100">{{ news.title || '暂无标题' }}</div>
                <div class="mt-1 text-sm text-slate-400">{{ news.summary || '暂无摘要' }}</div>
              </div>
              <div v-if="!currentItem.context.news.length" class="rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 p-3 text-sm text-slate-500">暂无新闻/题材上下文。</div>
            </div>
          </div>
        </div>
      </template>
      <EmptyPanel v-else title="暂无工作区图表" description="请先在自选管理里添加股票，或等待 Legacy 工作区同步。" />
    </AppCard>

    <div class="space-y-4">
      <AppCard title="自选股面板" subtitle="这里既是监控列表，也是工作区顺序控制入口。">
        <div v-if="watchlistQuery.isLoading.value"><LoadingSkeleton :lines="4" height="56px" /></div>
        <div v-else-if="watchlistItems.length" class="space-y-3">
          <div v-for="item in [...watchlistItems].sort((left, right) => left.sort_order - right.sort_order)" :key="item.id" class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
            <div class="flex items-start justify-between gap-3">
              <button class="text-left" @click="selectedSymbol = item.symbol">
                <div class="font-medium text-white">{{ item.display_name }}</div>
                <div class="mt-1 text-xs uppercase tracking-[0.22em] text-slate-500">{{ item.symbol }}</div>
              </button>
              <div class="text-right">
                <div class="text-sm text-white">{{ item.market?.last_price ?? '--' }}</div>
                <div class="text-xs" :class="(item.market?.change_pct ?? 0) >= 0 ? 'text-emerald-300' : 'text-rose-300'">{{ item.market?.change_pct == null ? '--' : formatPercent(item.market.change_pct) }}</div>
              </div>
            </div>
            <div class="mt-3 flex gap-2">
              <button class="btn-secondary flex-1" @click="moveSymbol(item.symbol, -1)">上移</button>
              <button class="btn-secondary flex-1" @click="moveSymbol(item.symbol, 1)">下移</button>
            </div>
          </div>
        </div>
        <EmptyPanel v-else title="暂无自选股" description="去自选管理添加股票后，这里会自动成为工作区顺序来源。" />
      </AppCard>

      <AppCard title="市场脉搏" subtitle="工作区外的共享市场视角。">
        <PulseChart v-if="pulseItems.length" :items="pulseItems" />
        <EmptyPanel v-else title="暂无共享脉搏" description="等待实时市场快照同步。" />
      </AppCard>
    </div>
  </div>
</template>
