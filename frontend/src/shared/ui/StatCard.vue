<script setup lang="ts">
defineProps<{ label: string; value: string; tone?: 'default' | 'positive' | 'negative' | 'brand' }>();

const toneClasses = {
  default: 'text-slate-100',
  positive: 'text-emerald-300',
  negative: 'text-rose-300',
  brand: 'text-indigo-300',
};
</script>

<template>
  <div class="glass-card p-4">
    <div class="text-xs uppercase tracking-[0.24em] text-slate-500">{{ label }}</div>
    <div class="mt-3 text-3xl font-semibold" :class="toneClasses[tone || 'default']">{{ value }}</div>
  </div>
</template>
