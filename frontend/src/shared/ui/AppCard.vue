<script setup lang="ts">
defineProps<{ title?: string; subtitle?: string }>();
</script>

<template>
  <section class="glass-card p-5">
    <div v-if="title" class="mb-4 flex items-start justify-between gap-3">
      <div>
        <h3 class="text-base font-semibold text-slate-100">{{ title }}</h3>
        <p v-if="subtitle" class="mt-1 text-sm text-slate-400">{{ subtitle }}</p>
      </div>
      <slot name="action" />
    </div>
    <slot />
  </section>
</template>
