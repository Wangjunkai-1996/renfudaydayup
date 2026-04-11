<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query';
import { computed } from 'vue';

import { apiClient } from '@/shared/api/client';
import type { PaperAccountPayload, PaperBaseConfigView } from '@/shared/api/types';
import { formatMoney, formatNumber, formatPercent } from '@/shared/lib/format';
import AppCard from '@/shared/ui/AppCard.vue';
import EmptyPanel from '@/shared/ui/EmptyPanel.vue';
import LoadingSkeleton from '@/shared/ui/LoadingSkeleton.vue';
import MetricCard from '@/shared/ui/MetricCard.vue';
import PageHeader from '@/shared/ui/PageHeader.vue';

const queryClient = useQueryClient();

const accountQuery = useQuery({ queryKey: ['paper-account'], queryFn: () => apiClient.get<PaperAccountPayload>('/api/v1/paper/account') });
const ordersQuery = useQuery({ queryKey: ['paper-orders'], queryFn: () => apiClient.get<{ success: boolean; items: Array<Record<string, unknown>> }>('/api/v1/paper/orders?limit=50') });

const resetMutation = useMutation({
  mutationFn: () => apiClient.post('/api/v1/paper/reset', { starting_cash: 800000 }),
  onSuccess: async () => {
    await queryClient.invalidateQueries({ queryKey: ['paper-account'] });
    await queryClient.invalidateQueries({ queryKey: ['paper-orders'] });
  },
});

const baseConfigMutation = useMutation({
  mutationFn: (payload: PaperBaseConfigView) => apiClient.put('/api/v1/paper/base-config', {
    symbol: payload.symbol,
    base_amount: payload.base_amount,
    base_cost: payload.base_cost,
    t_order_amount: payload.t_order_amount,
    t_daily_budget: payload.t_daily_budget,
    t_costline_strength: payload.t_costline_strength,
    enabled: payload.enabled,
  }),
  onSuccess: async () => {
    await queryClient.invalidateQueries({ queryKey: ['paper-account'] });
  },
});

const payload = computed(() => accountQuery.data.value ?? null);
const account = computed(() => payload.value?.account ?? null);
const positions = computed(() => payload.value?.positions ?? []);
const orders = computed<Array<Record<string, any>>>(() => ((ordersQuery.data.value?.items as Array<Record<string, any>> | undefined) ?? (payload.value?.orders as Array<Record<string, any>> | undefined) ?? []));
const baseConfigs = computed(() => payload.value?.base_configs ?? []);

function saveConfig(config: PaperBaseConfigView) {
  baseConfigMutation.mutate(config);
}

function resetAccount() {
  if (window.confirm('确认重置模拟账户？这会清空仓位和订单记录。')) {
    resetMutation.mutate();
  }
}
</script>

<template>
  <PageHeader title="模拟账户" subtitle="查看账户净值、持仓、订单与底仓配置。">
    <button class="btn-danger" @click="resetAccount">重置账户</button>
  </PageHeader>

  <div v-if="accountQuery.isLoading.value" class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
    <div v-for="index in 4" :key="index" class="glass-card p-5"><LoadingSkeleton :lines="2" height="20px" /></div>
  </div>
  <div v-else-if="account" class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
    <MetricCard label="起始资金" :value="formatMoney(account.starting_cash)" tone="brand" />
    <MetricCard label="可用现金" :value="formatMoney(account.cash)" tone="positive" />
    <MetricCard label="持仓市值" :value="formatMoney(account.market_value ?? 0)" />
    <MetricCard label="总收益率" :value="formatPercent(account.return_pct ?? 0)" :tone="(account.return_pct ?? 0) >= 0 ? 'positive' : 'negative'" />
  </div>

  <div class="mt-6 grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
    <AppCard title="当前持仓" subtitle="真实持仓、可用数量与盈亏一览。">
      <div v-if="positions.length" class="overflow-x-auto">
        <table class="panel-table">
          <thead>
            <tr>
              <th>股票</th>
              <th>数量</th>
              <th>可用</th>
              <th>成本</th>
              <th>现价</th>
              <th>浮盈亏</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="position in positions" :key="position.id">
              <td>
                <div class="font-medium text-white">{{ position.name }}</div>
                <div class="mt-1 text-xs uppercase tracking-[0.24em] text-slate-500">{{ position.symbol }}</div>
              </td>
              <td>{{ position.quantity }}</td>
              <td>{{ position.available_quantity }}</td>
              <td>{{ formatNumber(position.avg_cost) }}</td>
              <td>{{ formatNumber(position.last_price) }}</td>
              <td :class="(position.unrealized_pnl ?? 0) >= 0 ? 'text-emerald-300' : 'text-rose-300'">{{ formatMoney(position.unrealized_pnl ?? 0) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <EmptyPanel v-else title="暂无持仓" description="当前模拟账户没有持仓记录。" />
    </AppCard>

    <AppCard title="底仓配置" subtitle="管理底仓金额、成本线、单笔 T 额度和每日预算。">
      <div v-if="baseConfigs.length" class="space-y-3">
        <div v-for="config in baseConfigs" :key="config.id" class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          <div class="mb-4 flex items-center justify-between gap-3">
            <div>
              <div class="font-medium text-white">{{ config.name || config.symbol }}</div>
              <div class="mt-1 text-xs uppercase tracking-[0.24em] text-slate-500">{{ config.symbol }}</div>
            </div>
            <label class="flex items-center gap-2 text-sm text-slate-300">
              <input v-model="config.enabled" type="checkbox" />
              启用
            </label>
          </div>
          <div class="grid gap-3 md:grid-cols-2">
            <input v-model.number="config.base_amount" class="input-base" placeholder="底仓金额" />
            <input v-model.number="config.base_cost" class="input-base" placeholder="成本线" />
            <input v-model.number="config.t_order_amount" class="input-base" placeholder="单笔 T 金额" />
            <input v-model.number="config.t_daily_budget" class="input-base" placeholder="每日 T 预算" />
            <input v-model.number="config.t_costline_strength" class="input-base" placeholder="成本线强度" />
            <button class="btn-primary" @click="saveConfig(config)">保存配置</button>
          </div>
        </div>
      </div>
      <EmptyPanel v-else title="暂无底仓配置" description="先生成底仓配置后，这里会显示可编辑表单。" />
    </AppCard>
  </div>

  <AppCard class="mt-6" title="最近订单" subtitle="查看最新模拟单、信号关联与拒绝原因。">
    <div v-if="orders.length" class="overflow-x-auto">
      <table class="panel-table">
        <thead>
          <tr>
            <th>时间</th>
            <th>股票</th>
            <th>方向</th>
            <th>状态</th>
            <th>数量</th>
            <th>价格</th>
            <th>原因</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="order in orders" :key="String(order.id || order.order_id)">
            <td>{{ String(order.created_at || '--') }}</td>
            <td>
              <div class="font-medium text-white">{{ String(order.name || order.symbol || '--') }}</div>
              <div class="mt-1 text-xs uppercase tracking-[0.24em] text-slate-500">{{ String(order.symbol || '--') }}</div>
            </td>
            <td>{{ String(order.side || '--') }}</td>
            <td>{{ String(order.status || '--') }}</td>
            <td>{{ Number(order.quantity || order.qty || 0) }}</td>
            <td>{{ formatNumber(Number(order.price || 0)) }}</td>
            <td class="max-w-[280px] text-slate-400">{{ String(order.reason || '--') }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <EmptyPanel v-else title="暂无订单" description="当前没有模拟订单记录。" />
  </AppCard>
</template>
