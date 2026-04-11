<script setup lang="ts">
import AppCard from '@/shared/ui/AppCard.vue';
defineProps<{ title?: string; subtitle?: string }>();
</script>

<template>
  <AppCard :title="title" :subtitle="subtitle">
    <slot />
  </AppCard>
</template>
