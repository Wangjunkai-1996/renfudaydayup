<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query';
import { computed } from 'vue';

import { apiClient } from '@/shared/api/client';
import AppCard from '@/shared/ui/AppCard.vue';
import PageHeader from '@/shared/ui/PageHeader.vue';

const historyQuery = useQuery({ queryKey: ['reports-history'], queryFn: () => apiClient.get<{ daily_stats: Array<any>; signals: Array<any> }>('/api/v1/reports/history') });
const dailyListQuery = useQuery({ queryKey: ['reports-daily-list'], queryFn: () => apiClient.get<Array<any>>('/api/v1/reports/daily/list') });
const dailyStats = computed(() => historyQuery.data.value?.daily_stats ?? []);
const dailyReports = computed(() => dailyListQuery.data.value ?? []);
</script>

<template>
  <PageHeader title="Reports" subtitle="历史复盘、日报与 bundle 的独立页面化承载。" />
  <div class="grid gap-4 xl:grid-cols-[0.8fr_1.2fr]">
    <AppCard title="Daily Stats">
      <div class="space-y-3 text-sm text-slate-300">
        <div v-for="item in dailyStats" :key="String(item.date)" class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          {{ item.date }} · 胜率 {{ item.win_rate }}% · 总 {{ item.total }}
        </div>
      </div>
    </AppCard>
    <AppCard title="Daily Reports">
      <div class="space-y-3 text-sm text-slate-300">
        <div v-for="item in dailyReports" :key="String(item.id)" class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          {{ item.trade_date }} · {{ item.title }}
        </div>
      </div>
    </AppCard>
  </div>
</template>
