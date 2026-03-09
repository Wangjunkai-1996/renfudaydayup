<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { useRoute } from 'vue-router';

import AppShell from '@/shared/layouts/AppShell.vue';
import { useAuthStore } from '@/shared/stores/auth';

const route = useRoute();
const authStore = useAuthStore();
const isPublicPage = computed(() => Boolean(route.meta.public));

onMounted(() => {
  authStore.bootstrap();
});
</script>

<template>
  <RouterView v-slot="{ Component }">
    <component :is="Component" v-if="isPublicPage" />
    <AppShell v-else>
      <component :is="Component" />
    </AppShell>
  </RouterView>
</template>
