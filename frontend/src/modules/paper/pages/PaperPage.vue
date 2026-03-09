<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query';
import { computed } from 'vue';

import { apiClient } from '@/shared/api/client';
import { formatMoney } from '@/shared/lib/format';
import AppCard from '@/shared/ui/AppCard.vue';
import PageHeader from '@/shared/ui/PageHeader.vue';

const accountQuery = useQuery({ queryKey: ['paper-account'], queryFn: () => apiClient.get<{ account: { cash: number; starting_cash: number; realized_pnl: number }; positions: Array<any>; orders: Array<any> }>('/api/v1/paper/account') });
const baseConfigQuery = useQuery({ queryKey: ['paper-base-config'], queryFn: () => apiClient.get<Array<any>>('/api/v1/paper/base-config') });
const account = computed(() => accountQuery.data.value?.account ?? { cash: 0, starting_cash: 0, realized_pnl: 0 });
const positions = computed(() => accountQuery.data.value?.positions ?? []);
const baseConfigs = computed(() => baseConfigQuery.data.value ?? []);
</script>

<template>
  <PageHeader title="Paper" subtitle="模拟交易账户、持仓、订单与底仓配置。" />
  <div class="grid gap-4 xl:grid-cols-3">
    <AppCard title="Account">
      <div class="space-y-2 text-sm text-slate-300">
        <div>Starting Cash: {{ formatMoney(account.starting_cash) }}</div>
        <div>Cash: {{ formatMoney(account.cash) }}</div>
        <div>Realized PnL: {{ formatMoney(account.realized_pnl) }}</div>
      </div>
    </AppCard>
    <AppCard title="Positions">
      <div class="space-y-3">
        <div v-for="position in positions" :key="String(position.id)" class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4 text-sm text-slate-300">
          {{ position.symbol }} · {{ position.quantity }} 股 @ {{ position.avg_cost }}
        </div>
      </div>
    </AppCard>
    <AppCard title="Base Config">
      <div class="space-y-3 text-sm text-slate-300">
        <div v-for="config in baseConfigs" :key="String(config.id)" class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          {{ config.symbol }} · base {{ config.base_amount }} · t-order {{ config.t_order_amount }}
        </div>
      </div>
    </AppCard>
  </div>
</template>
