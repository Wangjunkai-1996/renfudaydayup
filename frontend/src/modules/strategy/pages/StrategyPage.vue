<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query';
import { computed, ref, watch } from 'vue';

import { apiClient } from '@/shared/api/client';
import AppCard from '@/shared/ui/AppCard.vue';
import PageHeader from '@/shared/ui/PageHeader.vue';

const queryClient = useQueryClient();
const label = ref('');
const rawConfig = ref('{}');

const configQuery = useQuery({ queryKey: ['strategy-config'], queryFn: () => apiClient.get<{ config_json: Record<string, any> }>('/api/v1/strategy/config') });
const snapshotQuery = useQuery({ queryKey: ['strategy-snapshots'], queryFn: () => apiClient.get<Array<any>>('/api/v1/strategy/snapshots') });
const snapshots = computed(() => snapshotQuery.data.value ?? []);

watch(
  () => configQuery.data.value?.config_json,
  (value) => {
    if (value) {
      rawConfig.value = JSON.stringify(value, null, 2);
    }
  },
  { immediate: true },
);

const saveMutation = useMutation({
  mutationFn: () => apiClient.put('/api/v1/strategy/config', { config_json: JSON.parse(rawConfig.value) }),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ['strategy-config'] }),
});

const snapshotMutation = useMutation({
  mutationFn: () => apiClient.post('/api/v1/strategy/snapshots', { label: label.value }),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ['strategy-snapshots'] }),
});

async function rollback(snapshotId: string) {
  await apiClient.post('/api/v1/strategy/rollback', { snapshot_id: snapshotId });
  await queryClient.invalidateQueries({ queryKey: ['strategy-config'] });
}

const parsedPreview = computed(() => {
  try {
    return JSON.parse(rawConfig.value);
  } catch {
    return { error: '当前 JSON 无法解析' };
  }
});
</script>

<template>
  <PageHeader title="Strategy" subtitle="用户私有参数、快照保存与回滚入口。" />
  <div class="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
    <AppCard title="Config Editor" subtitle="先用 JSON 版配置，后续再拆分成结构化表单。">
      <textarea v-model="rawConfig" class="min-h-[420px] w-full rounded-2xl border border-slate-700 bg-slate-950/70 p-4 text-sm text-slate-200 outline-none focus:border-indigo-400"></textarea>
      <div class="mt-4 flex gap-3">
        <button class="rounded-2xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500" @click="saveMutation.mutate()">保存配置</button>
      </div>
      <pre class="mt-4 overflow-auto rounded-2xl border border-slate-800 bg-slate-950/60 p-4 text-xs text-slate-400">{{ JSON.stringify(parsedPreview, null, 2) }}</pre>
    </AppCard>
    <AppCard title="Snapshots" subtitle="策略快照和快速回滚。">
      <div class="flex gap-3">
        <input v-model="label" class="flex-1 rounded-2xl border border-slate-700 bg-slate-950/70 px-4 py-2 text-sm text-white outline-none focus:border-indigo-400" placeholder="快照名称" />
        <button class="rounded-2xl bg-slate-800 px-4 py-2 text-sm text-white hover:bg-slate-700" @click="snapshotMutation.mutate()">保存快照</button>
      </div>
      <div class="mt-4 space-y-3">
        <div v-for="snapshot in snapshots" :key="String(snapshot.id)" class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          <div class="flex items-center justify-between gap-3">
            <div>
              <div class="font-medium text-white">{{ snapshot.label }}</div>
              <div class="mt-1 text-xs text-slate-500">{{ snapshot.created_at }}</div>
            </div>
            <button class="rounded-2xl bg-indigo-500/20 px-3 py-2 text-sm text-indigo-100 hover:bg-indigo-500/30" @click="rollback(String(snapshot.id))">回滚</button>
          </div>
        </div>
      </div>
    </AppCard>
  </div>
</template>
