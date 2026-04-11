<script setup lang="ts">
defineProps<{ label: string; value: string; helper?: string; tone?: 'default' | 'positive' | 'negative' | 'brand' }>();

const toneMap = {
  default: 'text-white',
  positive: 'text-emerald-300',
  negative: 'text-rose-300',
  brand: 'text-indigo-300',
};
</script>

<template>
  <div class="glass-card p-5">
    <div class="text-xs uppercase tracking-[0.24em] text-slate-500">{{ label }}</div>
    <div class="mt-3 text-3xl font-semibold" :class="toneMap[tone || 'default']">{{ value }}</div>
    <div v-if="helper" class="mt-2 text-sm text-slate-400">{{ helper }}</div>
  </div>
</template>
