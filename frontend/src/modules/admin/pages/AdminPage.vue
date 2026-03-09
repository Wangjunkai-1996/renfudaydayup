<script setup lang="ts">
import { computed } from 'vue';
import { useQuery } from '@tanstack/vue-query';

import { apiClient } from '@/shared/api/client';
import AppCard from '@/shared/ui/AppCard.vue';
import PageHeader from '@/shared/ui/PageHeader.vue';

const usersQuery = useQuery({ queryKey: ['admin-users'], queryFn: () => apiClient.get<Array<any>>('/api/v1/admin/users') });
const healthQuery = useQuery({ queryKey: ['system-health'], queryFn: () => apiClient.get<Record<string, any>>('/api/v1/system/health') });
const users = computed(() => usersQuery.data.value ?? []);
const health = computed(() => healthQuery.data.value ?? {});
</script>

<template>
  <PageHeader title="Admin" subtitle="管理员用户和系统健康总览。" />
  <div class="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
    <AppCard title="Users">
      <div class="space-y-3 text-sm text-slate-300">
        <div v-for="user in users" :key="String(user.id)" class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          {{ user.username }} · {{ user.role }} · {{ user.is_active ? 'active' : 'disabled' }}
        </div>
      </div>
    </AppCard>
    <AppCard title="System Health"><pre class="text-xs text-slate-300">{{ JSON.stringify(health, null, 2) }}</pre></AppCard>
  </div>
</template>
