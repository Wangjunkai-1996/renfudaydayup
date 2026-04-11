<script setup lang="ts">
defineProps<{ title?: string; message: string }>();
</script>

<template>
  <div class="rounded-3xl border border-rose-500/30 bg-rose-500/10 p-5 text-sm text-rose-100">
    <div class="font-semibold">{{ title || '加载失败' }}</div>
    <div class="mt-2 text-rose-200/90">{{ message }}</div>
  </div>
</template>
