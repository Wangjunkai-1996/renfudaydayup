<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query';
import { computed, ref } from 'vue';

import { apiClient } from '@/shared/api/client';
import type { WatchlistItem } from '@/shared/api/types';
import { formatNumber, formatPercent } from '@/shared/lib/format';
import { useRealtimeStore } from '@/shared/stores/realtime';
import AppCard from '@/shared/ui/AppCard.vue';
import EmptyPanel from '@/shared/ui/EmptyPanel.vue';
import ErrorPanel from '@/shared/ui/ErrorPanel.vue';
import LoadingSkeleton from '@/shared/ui/LoadingSkeleton.vue';
import MetricCard from '@/shared/ui/MetricCard.vue';
import PageHeader from '@/shared/ui/PageHeader.vue';
import StateBadge from '@/shared/ui/StateBadge.vue';

interface SearchInstrument {
  symbol: string;
  name: string;
  exchange?: string;
  sector?: string;
}

const queryClient = useQueryClient();
const realtimeStore = useRealtimeStore();
const keyword = ref('');
const symbol = ref('');
const message = ref('');
const pageError = ref('');

const watchlistQuery = useQuery({
  queryKey: ['watchlist-market'],
  queryFn: () => apiClient.get<WatchlistItem[]>('/api/v1/market/watchlist'),
});

const searchQuery = useQuery({
  queryKey: ['instrument-search', keyword],
  enabled: false,
  queryFn: () => apiClient.get<SearchInstrument[]>(`/api/v1/instruments/search?q=${encodeURIComponent(keyword.value.trim())}`),
});

const watchlistItems = computed(() => watchlistQuery.data.value ?? []);
const searchItems = computed(() => searchQuery.data.value ?? []);
const quoteMap = computed(() => new Map(realtimeStore.watchlistQuotes.map((item) => [item.symbol, item])));

const addMutation = useMutation({
  mutationFn: (target: string) => apiClient.post('/api/v1/watchlist', { symbol: target }),
  onSuccess: async () => {
    message.value = '已加入自选并同步到工作区顺序。';
    symbol.value = '';
    pageError.value = '';
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['watchlist-market'] }),
      queryClient.invalidateQueries({ queryKey: ['market-workbench'] }),
      queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] }),
    ]);
  },
  onError: (error) => {
    pageError.value = error instanceof Error ? error.message : '添加自选失败';
  },
});

const removeMutation = useMutation({
  mutationFn: (target: string) => apiClient.delete(`/api/v1/watchlist/${target}`),
  onSuccess: async () => {
    message.value = '已从自选中移除。';
    pageError.value = '';
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['watchlist-market'] }),
      queryClient.invalidateQueries({ queryKey: ['market-workbench'] }),
      queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] }),
    ]);
  },
  onError: (error) => {
    pageError.value = error instanceof Error ? error.message : '删除自选失败';
  },
});

const reorderMutation = useMutation({
  mutationFn: (symbols: string[]) => apiClient.post('/api/v1/watchlist/reorder', { symbols }),
  onSuccess: async () => {
    message.value = '工作区顺序已保存。';
    pageError.value = '';
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['watchlist-market'] }),
      queryClient.invalidateQueries({ queryKey: ['market-workbench'] }),
      queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] }),
    ]);
  },
  onError: (error) => {
    pageError.value = error instanceof Error ? error.message : '保存排序失败';
  },
});

const firstSymbol = computed(() => watchlistItems.value[0]?.symbol || '--');
const risingCount = computed(() => watchlistItems.value.filter((item) => currentChange(item) > 0).length);

function currentPrice(item: WatchlistItem): number | null {
  const quote = quoteMap.value.get(item.symbol);
  return quote?.last_price ?? item.market?.last_price ?? null;
}

function currentChange(item: WatchlistItem): number {
  const quote = quoteMap.value.get(item.symbol);
  return quote?.change_pct ?? item.market?.change_pct ?? 0;
}

function runSearch() {
  if (!keyword.value.trim()) {
    pageError.value = '请输入股票代码或名称后再搜索。';
    return;
  }
  pageError.value = '';
  message.value = '';
  searchQuery.refetch();
}

function addCurrentSymbol() {
  const target = symbol.value.trim().toLowerCase();
  if (!target) {
    pageError.value = '请输入要加入自选的股票代码。';
    return;
  }
  addMutation.mutate(target);
}

function quickAdd(target: string) {
  symbol.value = target;
  addMutation.mutate(target.toLowerCase());
}

function seedSymbol(target: string) {
  symbol.value = target;
  message.value = `已带入 ${target}，点击右侧按钮即可加入自选。`;
}

function moveItem(index: number, direction: -1 | 1) {
  const nextIndex = index + direction;
  if (nextIndex < 0 || nextIndex >= watchlistItems.value.length || reorderMutation.isPending.value) {
    return;
  }
  const items = [...watchlistItems.value];
  const [moved] = items.splice(index, 1);
  items.splice(nextIndex, 0, moved);
  reorderMutation.mutate(items.map((item) => item.symbol));
}
</script>

<template>
  <PageHeader title="自选管理" subtitle="搜索股票、维护顺序，并把首屏展示顺序同步到盯盘工作区。" />

  <div class="mb-6 grid gap-4 md:grid-cols-3">
    <MetricCard label="自选总数" :value="String(watchlistItems.length)" helper="所有股票仅属于当前登录用户" tone="brand" />
    <MetricCard label="默认首屏" :value="firstSymbol" helper="Market 与 Dashboard 默认按此顺序展开" />
    <MetricCard label="上涨家数" :value="String(risingCount)" helper="来自自选最新快照或实时报价" :tone="risingCount > 0 ? 'positive' : 'default'" />
  </div>

  <div v-if="pageError" class="mb-4">
    <ErrorPanel :message="pageError" />
  </div>
  <div v-else-if="message" class="mb-4 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
    {{ message }}
  </div>

  <div class="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
    <AppCard title="股票搜索与添加" subtitle="先搜后加，避免输错代码。支持从搜索结果一键加入自选。">
      <div class="flex gap-3">
        <input v-model="keyword" class="input-base" placeholder="输入股票代码、名称或拼音关键字" @keyup.enter="runSearch" />
        <button class="btn-secondary" @click="runSearch">搜索</button>
      </div>

      <div class="mt-4" v-if="searchQuery.isLoading.value">
        <LoadingSkeleton :lines="5" height="54px" />
      </div>
      <div v-else-if="searchItems.length" class="mt-4 space-y-3">
        <div v-for="item in searchItems" :key="item.symbol" class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          <div class="flex items-start justify-between gap-3">
            <div>
              <div class="text-base font-semibold text-white">{{ item.name || item.symbol }}</div>
              <div class="mt-1 text-xs uppercase tracking-[0.24em] text-slate-500">{{ item.symbol }}</div>
              <div class="mt-2 flex flex-wrap gap-2">
                <StateBadge :label="item.exchange || 'CN'" tone="default" />
                <StateBadge :label="item.sector || '未分类行业'" tone="brand" />
              </div>
            </div>
            <div class="flex gap-2">
              <button class="btn-secondary" @click="seedSymbol(item.symbol)">带入添加框</button>
              <button class="btn-primary" @click="quickAdd(item.symbol)">加入自选</button>
            </div>
          </div>
        </div>
      </div>
      <EmptyPanel v-else title="先搜一只股票" description="搜索结果会展示名称、交易所和行业，并支持一键加入自选。" />

      <div class="mt-6 border-t border-slate-800 pt-6">
        <div class="mb-3 text-sm font-semibold text-white">手动添加</div>
        <div class="flex gap-3">
          <input v-model="symbol" class="input-base" placeholder="例如 sz002438 / sh600079" @keyup.enter="addCurrentSymbol" />
          <button class="btn-primary" @click="addCurrentSymbol">添加到自选</button>
        </div>
      </div>
    </AppCard>

    <AppCard title="我的自选与工作区顺序" subtitle="第一只股票会作为 Dashboard 和 Market 的默认焦点股。">
      <div v-if="watchlistQuery.isLoading.value">
        <LoadingSkeleton :lines="6" height="76px" />
      </div>
      <div v-else-if="watchlistItems.length" class="space-y-3">
        <div
          v-for="(item, index) in watchlistItems"
          :key="item.id"
          class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4"
        >
          <div class="flex items-start justify-between gap-3">
            <div>
              <div class="flex flex-wrap items-center gap-2">
                <div class="text-base font-semibold text-white">{{ item.display_name || item.symbol }}</div>
                <StateBadge v-if="index === 0" label="首屏默认" tone="brand" />
              </div>
              <div class="mt-1 text-xs uppercase tracking-[0.24em] text-slate-500">{{ item.symbol }}</div>
              <div class="mt-3 grid gap-3 md:grid-cols-3">
                <div>
                  <div class="text-xs uppercase tracking-[0.2em] text-slate-500">最新价</div>
                  <div class="mt-1 text-sm text-white">{{ formatNumber(currentPrice(item), 3) }}</div>
                </div>
                <div>
                  <div class="text-xs uppercase tracking-[0.2em] text-slate-500">涨跌幅</div>
                  <div class="mt-1 text-sm" :class="currentChange(item) >= 0 ? 'text-emerald-300' : 'text-rose-300'">{{ formatPercent(currentChange(item)) }}</div>
                </div>
                <div>
                  <div class="text-xs uppercase tracking-[0.2em] text-slate-500">排序位</div>
                  <div class="mt-1 text-sm text-white">第 {{ index + 1 }} 位</div>
                </div>
              </div>
            </div>
            <div class="flex flex-wrap gap-2">
              <button class="btn-secondary" :disabled="index === 0" @click="moveItem(index, -1)">上移</button>
              <button class="btn-secondary" :disabled="index === watchlistItems.length - 1" @click="moveItem(index, 1)">下移</button>
              <button class="rounded-2xl bg-rose-500/10 px-4 py-2 text-sm font-medium text-rose-200 hover:bg-rose-500/20" @click="removeMutation.mutate(item.symbol)">删除</button>
            </div>
          </div>
        </div>
      </div>
      <EmptyPanel v-else title="还没有自选股票" description="添加至少一只股票后，Market 工作区会自动按你的顺序展开。" />
    </AppCard>
  </div>
</template>
