<script setup lang="ts">
defineProps<{ lines?: number; height?: string }>();
</script>

<template>
  <div class="space-y-3">
    <div
      v-for="index in lines || 3"
      :key="index"
      class="animate-pulse rounded-2xl bg-slate-800/80"
      :style="{ height: height || '16px' }"
    />
  </div>
</template>
