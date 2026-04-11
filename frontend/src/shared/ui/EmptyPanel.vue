<script setup lang="ts">
defineProps<{ title: string; description: string }>();
</script>

<template>
  <div class="rounded-3xl border border-dashed border-slate-700 bg-slate-950/40 p-8 text-center">
    <div class="text-base font-semibold text-slate-200">{{ title }}</div>
    <div class="mt-2 text-sm text-slate-400">{{ description }}</div>
  </div>
</template>
