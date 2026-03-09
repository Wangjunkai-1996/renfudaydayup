<script setup lang="ts">
defineProps<{ title: string; subtitle: string }>();
</script>

<template>
  <div class="mb-6 flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
    <div>
      <h1 class="text-3xl font-bold tracking-tight text-white">{{ title }}</h1>
      <p class="mt-1 text-sm text-slate-400">{{ subtitle }}</p>
    </div>
    <slot />
  </div>
</template>
