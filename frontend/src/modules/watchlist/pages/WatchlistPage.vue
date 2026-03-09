<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query';
import { computed, ref } from 'vue';

import { apiClient } from '@/shared/api/client';
import AppCard from '@/shared/ui/AppCard.vue';
import PageHeader from '@/shared/ui/PageHeader.vue';

const queryClient = useQueryClient();
const keyword = ref('');
const symbol = ref('');

const watchlistQuery = useQuery({ queryKey: ['watchlist-market'], queryFn: () => apiClient.get<Array<any>>('/api/v1/market/watchlist') });
const searchQuery = useQuery({ queryKey: ['instrument-search', keyword], enabled: false, queryFn: () => apiClient.get<Array<any>>(`/api/v1/instruments/search?q=${encodeURIComponent(keyword.value)}`) });
const watchlistItems = computed(() => watchlistQuery.data.value ?? []);
const searchItems = computed(() => searchQuery.data.value ?? []);

const addMutation = useMutation({
  mutationFn: () => apiClient.post('/api/v1/watchlist', { symbol: symbol.value }),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ['watchlist-market'] }),
});

const removeMutation = useMutation({
  mutationFn: (target: string) => apiClient.delete(`/api/v1/watchlist/${target}`),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ['watchlist-market'] }),
});
</script>

<template>
  <PageHeader title="Watchlist" subtitle="股票搜索、添加和用户私有自选管理。" />
  <div class="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
    <AppCard title="Instrument Search">
      <div class="flex gap-3">
        <input v-model="keyword" class="flex-1 rounded-2xl border border-slate-700 bg-slate-950/70 px-4 py-2 text-sm text-white outline-none focus:border-indigo-400" placeholder="代码 / 名称" />
        <button class="rounded-2xl bg-slate-800 px-4 py-2 text-sm text-white hover:bg-slate-700" @click="searchQuery.refetch()">搜索</button>
      </div>
      <div class="mt-4 space-y-3 text-sm text-slate-300">
        <div v-for="item in searchItems" :key="String(item.symbol)" class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          {{ item.symbol }} · {{ item.name }} · {{ item.sector }}
        </div>
      </div>
    </AppCard>
    <AppCard title="My Watchlist">
      <div class="flex gap-3">
        <input v-model="symbol" class="flex-1 rounded-2xl border border-slate-700 bg-slate-950/70 px-4 py-2 text-sm text-white outline-none focus:border-indigo-400" placeholder="输入股票代码" />
        <button class="rounded-2xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500" @click="addMutation.mutate()">添加</button>
      </div>
      <div class="mt-4 space-y-3">
        <div v-for="item in watchlistItems" :key="String(item.id)" class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          <div class="flex items-center justify-between gap-3">
            <div>
              <div class="font-medium text-white">{{ item.display_name }}</div>
              <div class="mt-1 text-xs uppercase tracking-[0.24em] text-slate-500">{{ item.symbol }}</div>
            </div>
            <button class="rounded-2xl bg-rose-500/10 px-3 py-2 text-sm text-rose-200 hover:bg-rose-500/20" @click="removeMutation.mutate(String(item.symbol))">删除</button>
          </div>
        </div>
      </div>
    </AppCard>
  </div>
</template>
