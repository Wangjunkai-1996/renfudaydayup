<script setup lang="ts">
defineProps<{ label: string; tone?: 'default' | 'positive' | 'negative' | 'warning' | 'brand' }>();

const toneMap = {
  default: 'border-slate-700 bg-slate-900/70 text-slate-300',
  positive: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
  negative: 'border-rose-500/30 bg-rose-500/10 text-rose-200',
  warning: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
  brand: 'border-indigo-500/30 bg-indigo-500/10 text-indigo-200',
};
</script>

<template>
  <span class="inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium" :class="toneMap[tone || 'default']">{{ label }}</span>
</template>
