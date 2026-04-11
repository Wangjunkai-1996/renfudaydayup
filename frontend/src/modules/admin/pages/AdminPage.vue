<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query';
import { computed, ref } from 'vue';

import { apiClient } from '@/shared/api/client';
import type { HealthPayload, User } from '@/shared/api/types';
import { formatDateTime } from '@/shared/lib/format';
import { useAuthStore } from '@/shared/stores/auth';
import AppCard from '@/shared/ui/AppCard.vue';
import EmptyPanel from '@/shared/ui/EmptyPanel.vue';
import ErrorPanel from '@/shared/ui/ErrorPanel.vue';
import LoadingSkeleton from '@/shared/ui/LoadingSkeleton.vue';
import MetricCard from '@/shared/ui/MetricCard.vue';
import PageHeader from '@/shared/ui/PageHeader.vue';
import StateBadge from '@/shared/ui/StateBadge.vue';

const authStore = useAuthStore();
const queryClient = useQueryClient();

const createUsername = ref('');
const createPassword = ref('');
const createRole = ref<'user' | 'admin'>('user');
const resetPasswords = ref<Record<string, string>>({});
const feedback = ref('');
const pageError = ref('');

const usersQuery = useQuery({
  queryKey: ['admin-users'],
  queryFn: () => apiClient.get<User[]>('/api/v1/admin/users'),
});

const healthQuery = useQuery({
  queryKey: ['system-health'],
  queryFn: () => apiClient.get<HealthPayload>('/api/v1/system/health'),
});

const users = computed(() => usersQuery.data.value ?? []);
const activeCount = computed(() => users.value.filter((user) => user.is_active).length);
const adminCount = computed(() => users.value.filter((user) => user.role === 'admin').length);

const createUserMutation = useMutation({
  mutationFn: () => apiClient.post<User>('/api/v1/admin/users', { username: createUsername.value.trim(), password: createPassword.value, role: createRole.value }),
  onSuccess: async () => {
    feedback.value = '新用户已创建。';
    pageError.value = '';
    createUsername.value = '';
    createPassword.value = '';
    createRole.value = 'user';
    await queryClient.invalidateQueries({ queryKey: ['admin-users'] });
  },
  onError: (error) => {
    pageError.value = error instanceof Error ? error.message : '创建用户失败';
  },
});

const toggleUserMutation = useMutation({
  mutationFn: (payload: { userId: string; is_active: boolean }) => apiClient.patch<User>(`/api/v1/admin/users/${payload.userId}/state`, { is_active: payload.is_active }),
  onSuccess: async () => {
    feedback.value = '用户状态已更新。';
    pageError.value = '';
    await queryClient.invalidateQueries({ queryKey: ['admin-users'] });
  },
  onError: (error) => {
    pageError.value = error instanceof Error ? error.message : '更新用户状态失败';
  },
});

const resetPasswordMutation = useMutation({
  mutationFn: (payload: { userId: string; password: string }) => apiClient.post(`/api/v1/admin/users/${payload.userId}/reset-password`, { password: payload.password }),
  onSuccess: async (_, variables) => {
    feedback.value = '密码已重置。';
    pageError.value = '';
    resetPasswords.value = { ...resetPasswords.value, [variables.userId]: '' };
    await queryClient.invalidateQueries({ queryKey: ['admin-users'] });
  },
  onError: (error) => {
    pageError.value = error instanceof Error ? error.message : '重置密码失败';
  },
});

function submitCreate() {
  if (!createUsername.value.trim() || !createPassword.value.trim()) {
    pageError.value = '请输入用户名和初始密码。';
    return;
  }
  pageError.value = '';
  createUserMutation.mutate();
}

function submitReset(userId: string) {
  const password = resetPasswords.value[userId] || '';
  if (!password.trim()) {
    pageError.value = '请输入新的密码后再提交重置。';
    return;
  }
  pageError.value = '';
  resetPasswordMutation.mutate({ userId, password });
}
</script>

<template>
  <PageHeader title="管理后台" subtitle="在新 UI 内完成用户创建、启停、密码重置和系统健康查看。" />

  <div class="mb-6 grid gap-4 md:grid-cols-4">
    <MetricCard label="用户总数" :value="String(users.length)" helper="当前数据库中的账号数量" tone="brand" />
    <MetricCard label="启用账号" :value="String(activeCount)" helper="可正常登录的账号数" :tone="activeCount ? 'positive' : 'default'" />
    <MetricCard label="管理员" :value="String(adminCount)" helper="拥有后台权限的账号数" />
    <MetricCard label="系统状态" :value="healthQuery.data.value?.status || '--'" helper="健康检查来自 /api/v1/system/health" :tone="healthQuery.data.value?.status === 'ok' ? 'positive' : 'negative'" />
  </div>

  <div v-if="pageError" class="mb-4">
    <ErrorPanel :message="pageError" />
  </div>
  <div v-else-if="feedback" class="mb-4 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
    {{ feedback }}
  </div>

  <div class="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
    <AppCard title="创建新用户" subtitle="支持创建普通用户或管理员，后续再扩展更复杂的权限模型。">
      <div class="space-y-4">
        <input v-model="createUsername" class="input-base" placeholder="用户名" />
        <input v-model="createPassword" type="password" class="input-base" placeholder="初始密码" />
        <select v-model="createRole" class="input-base">
          <option value="user">普通用户</option>
          <option value="admin">管理员</option>
        </select>
        <button class="btn-primary" @click="submitCreate">创建账号</button>
      </div>
    </AppCard>

    <AppCard title="系统健康" subtitle="确认 API、数据库等核心组件已连通。">
      <div v-if="healthQuery.isLoading.value"><LoadingSkeleton :lines="6" height="18px" /></div>
      <template v-else>
        <div class="flex flex-wrap gap-2">
          <StateBadge :label="healthQuery.data.value?.status === 'ok' ? '运行正常' : '需要关注'" :tone="healthQuery.data.value?.status === 'ok' ? 'positive' : 'negative'" />
          <StateBadge :label="`检查时间 ${formatDateTime(healthQuery.data.value?.ts || '')}`" tone="default" />
        </div>
        <div class="mt-4 grid gap-3 md:grid-cols-2">
          <div v-for="(state, name) in healthQuery.data.value?.components || {}" :key="name" class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
            <div class="text-xs uppercase tracking-[0.24em] text-slate-500">{{ name }}</div>
            <div class="mt-2 text-base font-semibold text-white">{{ state }}</div>
          </div>
        </div>
      </template>
    </AppCard>
  </div>

  <div class="mt-6">
    <AppCard title="用户列表" subtitle="可直接启用/停用账号，并对单个用户执行密码重置。">
      <div v-if="usersQuery.isLoading.value"><LoadingSkeleton :lines="8" height="84px" /></div>
      <div v-else-if="users.length" class="space-y-3">
        <div v-for="user in users" :key="user.id" class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          <div class="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
            <div>
              <div class="flex flex-wrap items-center gap-2">
                <div class="text-base font-semibold text-white">{{ user.username }}</div>
                <StateBadge :label="user.role === 'admin' ? '管理员' : '普通用户'" :tone="user.role === 'admin' ? 'brand' : 'default'" />
                <StateBadge :label="user.is_active ? '已启用' : '已停用'" :tone="user.is_active ? 'positive' : 'negative'" />
                <StateBadge v-if="authStore.user?.id === user.id" label="当前会话" tone="warning" />
              </div>
              <div class="mt-2 text-sm text-slate-400">创建于 {{ formatDateTime(user.created_at) }} · 最近更新 {{ formatDateTime(user.updated_at) }}</div>
            </div>
            <div class="flex flex-1 flex-col gap-3 xl:max-w-[520px]">
              <div class="flex flex-wrap gap-2">
                <button
                  class="btn-secondary"
                  :disabled="authStore.user?.id === user.id"
                  @click="toggleUserMutation.mutate({ userId: user.id, is_active: !user.is_active })"
                >
                  {{ user.is_active ? '停用账号' : '启用账号' }}
                </button>
              </div>
              <div class="flex gap-2">
                <input
                  :value="resetPasswords[user.id] || ''"
                  class="input-base"
                  type="password"
                  placeholder="输入新密码"
                  @input="resetPasswords = { ...resetPasswords, [user.id]: ($event.target as HTMLInputElement).value }"
                />
                <button class="btn-primary" @click="submitReset(user.id)">重置密码</button>
              </div>
            </div>
          </div>
        </div>
      </div>
      <EmptyPanel v-else title="暂无用户" description="当前系统还没有可管理的用户记录。" />
    </AppCard>
  </div>
</template>
