<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query';
import { computed } from 'vue';

import { apiClient } from '@/shared/api/client';
import AppCard from '@/shared/ui/AppCard.vue';
import PageHeader from '@/shared/ui/PageHeader.vue';
import { useRealtimeStore } from '@/shared/stores/realtime';

const signalsQuery = useQuery({ queryKey: ['signals'], queryFn: () => apiClient.get<Array<any>>('/api/v1/signals') });
const realtimeStore = useRealtimeStore();
const signals = computed(() => (realtimeStore.hasSignals ? realtimeStore.signals : (signalsQuery.data.value ?? [])));
</script>

<template>
  <PageHeader title="Signals" subtitle="实时信号流、详情和解释入口。" />
  <AppCard title="LiveSignalRail" subtitle="迁移后的用户私有信号流。">
    <div class="mb-3 text-xs text-slate-500">实时流：{{ realtimeStore.connected ? '在线' : '离线' }}</div>
    <div class="space-y-3">
      <div v-for="item in signals" :key="String(item.id)" class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
        <div class="flex items-center justify-between gap-3">
          <div>
            <div class="font-medium text-white">{{ item.name }} · {{ item.symbol }}</div>
            <div class="mt-1 text-sm text-slate-400">{{ item.description }}</div>
          </div>
          <div class="text-right">
            <div class="text-sm font-semibold text-white">{{ item.side }}</div>
            <div class="mt-1 text-xs uppercase tracking-[0.2em] text-slate-500">{{ item.status }}</div>
          </div>
        </div>
      </div>
    </div>
  </AppCard>
</template>
