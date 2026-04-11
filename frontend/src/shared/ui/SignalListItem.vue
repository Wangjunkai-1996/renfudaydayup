<script setup lang="ts">
import type { SignalItem } from '@/shared/api/types';
import { formatDateTime, formatNumber } from '@/shared/lib/format';
import StateBadge from '@/shared/ui/StateBadge.vue';

defineProps<{ item: SignalItem; compact?: boolean }>();
</script>

<template>
  <div class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4 transition hover:border-slate-700 hover:bg-slate-900/80">
    <div class="flex items-start justify-between gap-4">
      <div>
        <div class="font-medium text-white">{{ item.name }} · {{ item.symbol }}</div>
        <div class="mt-1 text-sm text-slate-400">{{ item.description }}</div>
      </div>
      <div class="text-right">
        <StateBadge :label="item.side" :tone="item.side === 'BUY' ? 'positive' : 'negative'" />
        <div class="mt-2 text-xs text-slate-500">{{ formatDateTime(item.occurred_at) }}</div>
      </div>
    </div>
    <div class="mt-4 flex flex-wrap items-center gap-2 text-xs text-slate-400">
      <span>价格 {{ formatNumber(item.price) }}</span>
      <span>·</span>
      <span>级别 {{ item.level }}</span>
      <span>·</span>
      <span>状态 {{ item.status }}</span>
    </div>
  </div>
</template>
