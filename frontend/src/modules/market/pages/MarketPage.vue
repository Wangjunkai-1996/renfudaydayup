<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query';
import { computed } from 'vue';

import { apiClient } from '@/shared/api/client';
import AppCard from '@/shared/ui/AppCard.vue';
import PageHeader from '@/shared/ui/PageHeader.vue';
import PulseChart from '@/shared/ui/PulseChart.vue';
import { useRealtimeStore } from '@/shared/stores/realtime';

const pulseQuery = useQuery({ queryKey: ['market-pulse'], queryFn: () => apiClient.get<Array<{ symbol: string; name: string; last_price: number; change_pct: number }>>('/api/v1/market/pulse') });
const watchlistQuery = useQuery({ queryKey: ['market-watchlist'], queryFn: () => apiClient.get<Array<any>>('/api/v1/market/watchlist') });
const realtimeStore = useRealtimeStore();
const pulseItems = computed(() => (realtimeStore.hasPulse ? realtimeStore.pulse : (pulseQuery.data.value ?? [])));
const watchlistItems = computed(() => watchlistQuery.data.value ?? []);
</script>

<template>
  <PageHeader title="Market" subtitle="多股票工作区、共享市场脉搏和用户自选监控视图。" />
  <div class="grid gap-4 xl:grid-cols-[1.3fr_1fr]">
    <AppCard title="StockWorkbench" subtitle="这里将逐步替换旧首页 charts-wrapper 的职责。">
      <PulseChart :items="pulseItems" />
    </AppCard>
    <AppCard title="Watchlist Live Board" subtitle="自选股与最新市场快照。">
      <div class="space-y-3">
        <div v-for="item in watchlistItems" :key="String(item.id)" class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          <div class="flex items-center justify-between gap-3">
            <div>
              <div class="font-medium text-white">{{ item.display_name }}</div>
              <div class="mt-1 text-xs uppercase tracking-[0.22em] text-slate-500">{{ item.symbol }}</div>
            </div>
            <div class="text-right text-sm text-slate-300">
              <div>{{ item.market?.last_price ?? '--' }}</div>
              <div class="text-xs text-slate-500">{{ item.market?.change_pct ?? '--' }}%</div>
            </div>
          </div>
        </div>
      </div>
    </AppCard>
  </div>
</template>
