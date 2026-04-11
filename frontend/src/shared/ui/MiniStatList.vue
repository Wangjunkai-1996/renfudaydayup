<script setup lang="ts">
defineProps<{ items: Array<{ label: string; value: string }> }>();
</script>

<template>
  <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
    <div v-for="item in items" :key="item.label" class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
      <div class="text-xs uppercase tracking-[0.24em] text-slate-500">{{ item.label }}</div>
      <div class="mt-2 text-lg font-semibold text-white">{{ item.value }}</div>
    </div>
  </div>
</template>
