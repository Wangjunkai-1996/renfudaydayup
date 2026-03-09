<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query';

import { apiClient } from '@/shared/api/client';
import AppCard from '@/shared/ui/AppCard.vue';
import PageHeader from '@/shared/ui/PageHeader.vue';

const preflightQuery = useQuery({ queryKey: ['diag-preflight'], queryFn: () => apiClient.get<Record<string, unknown>>('/api/v1/diagnostics/preflight') });
const slotQuery = useQuery({ queryKey: ['diag-slot'], queryFn: () => apiClient.get<Record<string, unknown>>('/api/v1/diagnostics/slot-performance') });
const edgeQuery = useQuery({ queryKey: ['diag-edge'], queryFn: () => apiClient.get<Record<string, unknown>>('/api/v1/diagnostics/edge-diagnostics') });
</script>

<template>
  <PageHeader title="Diagnostics" subtitle="Preflight、时段表现和边际诊断集中展示。" />
  <div class="grid gap-4 xl:grid-cols-3">
    <AppCard title="Preflight"><pre class="text-xs text-slate-300">{{ JSON.stringify(preflightQuery.data ?? {}, null, 2) }}</pre></AppCard>
    <AppCard title="Slot Performance"><pre class="text-xs text-slate-300">{{ JSON.stringify(slotQuery.data ?? {}, null, 2) }}</pre></AppCard>
    <AppCard title="Edge Diagnostics"><pre class="text-xs text-slate-300">{{ JSON.stringify(edgeQuery.data ?? {}, null, 2) }}</pre></AppCard>
  </div>
</template>
