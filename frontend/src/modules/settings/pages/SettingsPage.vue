<script setup lang="ts">
import { useMutation, useQuery } from '@tanstack/vue-query';
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import { apiClient } from '@/shared/api/client';
import type { NotificationSettings } from '@/shared/api/types';
import { useAuthStore } from '@/shared/stores/auth';
import AppCard from '@/shared/ui/AppCard.vue';
import EmptyPanel from '@/shared/ui/EmptyPanel.vue';
import ErrorPanel from '@/shared/ui/ErrorPanel.vue';
import MetricCard from '@/shared/ui/MetricCard.vue';
import PageHeader from '@/shared/ui/PageHeader.vue';
import StateBadge from '@/shared/ui/StateBadge.vue';

const authStore = useAuthStore();
const router = useRouter();

const username = ref('');
const currentPassword = ref('');
const newPassword = ref('');
const confirmPassword = ref('');
const feedback = ref('');
const pageError = ref('');
const notificationDraft = ref<Record<string, boolean | string | number>>({});

const notificationsQuery = useQuery({
  queryKey: ['settings-notifications'],
  queryFn: () => apiClient.get<NotificationSettings>('/api/v1/settings/notifications'),
});

watch(
  () => authStore.user?.username,
  (value) => {
    username.value = value || '';
  },
  { immediate: true },
);

watch(
  () => notificationsQuery.data.value?.settings_json,
  (value) => {
    notificationDraft.value = { ...(value || {}) };
  },
  { immediate: true },
);

const notificationItems = computed(() => {
  const defaults: Array<{ key: string; label: string; desc: string }> = [
    { key: 'browser_push', label: '浏览器通知', desc: '桌面端弹出提醒' },
    { key: 'signal_alert', label: '信号提醒', desc: '新信号生成时优先提醒' },
    { key: 'preclose_alert', label: '尾盘提醒', desc: '尾盘前提醒处理持仓与信号' },
    { key: 'daily_report', label: '日报完成提醒', desc: '日报或 bundle 生成后提醒' },
    { key: 'system_notice', label: '系统通知', desc: '系统状态变更与维护提示' },
  ];
  return defaults.map((item) => ({ ...item, enabled: Boolean(notificationDraft.value[item.key]) }));
});

const accountMutation = useMutation({
  mutationFn: () => apiClient.put<{ username: string }>('/api/v1/settings/account', { username: username.value.trim() }),
  onSuccess: async (payload) => {
    if (authStore.user) {
      authStore.user = { ...authStore.user, username: payload.username };
    }
    feedback.value = '账户资料已更新。';
    pageError.value = '';
  },
  onError: (error) => {
    pageError.value = error instanceof Error ? error.message : '更新账户资料失败';
  },
});

const passwordMutation = useMutation({
  mutationFn: () => apiClient.put('/api/v1/settings/password', { current_password: currentPassword.value, new_password: newPassword.value }),
  onSuccess: () => {
    feedback.value = '密码已更新，其他设备需要重新登录。';
    pageError.value = '';
    currentPassword.value = '';
    newPassword.value = '';
    confirmPassword.value = '';
  },
  onError: (error) => {
    pageError.value = error instanceof Error ? error.message : '修改密码失败';
  },
});

const notificationsMutation = useMutation({
  mutationFn: () => apiClient.put<NotificationSettings>('/api/v1/settings/notifications', { settings_json: notificationDraft.value }),
  onSuccess: (payload) => {
    notificationDraft.value = { ...(payload.settings_json || {}) };
    feedback.value = '通知偏好已保存。';
    pageError.value = '';
  },
  onError: (error) => {
    pageError.value = error instanceof Error ? error.message : '保存通知偏好失败';
  },
});

const logoutAllMutation = useMutation({
  mutationFn: () => apiClient.post('/api/v1/settings/logout-all'),
  onSuccess: async () => {
    authStore.user = null;
    authStore.bootstrapped = true;
    await router.push('/login');
  },
  onError: (error) => {
    pageError.value = error instanceof Error ? error.message : '退出所有会话失败';
  },
});

function toggleNotification(key: string) {
  notificationDraft.value = {
    ...notificationDraft.value,
    [key]: !Boolean(notificationDraft.value[key]),
  };
}

function savePassword() {
  if (!currentPassword.value || !newPassword.value) {
    pageError.value = '请输入当前密码和新密码。';
    return;
  }
  if (newPassword.value !== confirmPassword.value) {
    pageError.value = '两次输入的新密码不一致。';
    return;
  }
  pageError.value = '';
  passwordMutation.mutate();
}
</script>

<template>
  <PageHeader title="账户设置" subtitle="维护账户资料、密码和通知偏好，并可一键清退所有会话。" />

  <div class="mb-6 grid gap-4 md:grid-cols-3">
    <MetricCard label="当前账号" :value="authStore.user?.username || '--'" helper="当前页面只展示登录用户自己的设置" tone="brand" />
    <MetricCard label="角色" :value="authStore.user?.role === 'admin' ? '管理员' : '普通用户'" helper="管理员可额外进入管理后台" />
    <MetricCard label="通知项" :value="String(notificationItems.filter((item) => item.enabled).length)" helper="已开启的提醒数量" :tone="notificationItems.filter((item) => item.enabled).length ? 'positive' : 'default'" />
  </div>

  <div v-if="pageError" class="mb-4">
    <ErrorPanel :message="pageError" />
  </div>
  <div v-else-if="feedback" class="mb-4 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
    {{ feedback }}
  </div>

  <div class="grid gap-4 xl:grid-cols-[1fr_1fr]">
    <AppCard title="账户资料" subtitle="仅允许修改当前登录名，角色和权限由管理员维护。">
      <div class="space-y-4">
        <label class="block text-sm text-slate-300">
          <div class="mb-2 text-sm font-medium text-white">用户名</div>
          <input v-model="username" class="input-base" placeholder="请输入用户名" />
        </label>
        <div class="flex items-center justify-between gap-3 rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          <div>
            <div class="text-sm font-semibold text-white">当前身份</div>
            <div class="mt-2 flex flex-wrap gap-2">
              <StateBadge :label="authStore.user?.role === 'admin' ? '管理员权限' : '用户权限'" tone="brand" />
              <StateBadge :label="authStore.user?.is_active ? '账号正常' : '账号已停用'" :tone="authStore.user?.is_active ? 'positive' : 'negative'" />
            </div>
          </div>
          <button class="btn-primary" @click="accountMutation.mutate()">保存资料</button>
        </div>
      </div>
    </AppCard>

    <AppCard title="密码与会话安全" subtitle="修改密码后会撤销其他设备会话，也支持主动清退所有会话。">
      <div class="space-y-4">
        <input v-model="currentPassword" type="password" class="input-base" placeholder="当前密码" />
        <input v-model="newPassword" type="password" class="input-base" placeholder="新密码（至少 6 位）" />
        <input v-model="confirmPassword" type="password" class="input-base" placeholder="再次输入新密码" />
        <div class="flex flex-wrap gap-3">
          <button class="btn-primary" @click="savePassword">修改密码</button>
          <button class="btn-secondary" @click="logoutAllMutation.mutate()">安全登出所有会话</button>
        </div>
      </div>
    </AppCard>
  </div>

  <div class="mt-6 grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
    <AppCard title="通知偏好" subtitle="按业务类型开启或关闭提醒，保存后立即生效。">
      <div v-if="notificationsQuery.isLoading.value" class="space-y-3">
        <div v-for="index in 5" :key="index" class="h-16 rounded-2xl border border-slate-800 bg-slate-950/60" />
      </div>
      <div v-else-if="notificationItems.length" class="space-y-3">
        <div v-for="item in notificationItems" :key="item.key" class="flex items-center justify-between gap-3 rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          <div>
            <div class="text-sm font-semibold text-white">{{ item.label }}</div>
            <div class="mt-1 text-sm text-slate-400">{{ item.desc }}</div>
          </div>
          <button
            class="rounded-2xl px-4 py-2 text-sm font-medium"
            :class="item.enabled ? 'bg-emerald-500/15 text-emerald-100' : 'bg-slate-800 text-slate-300'"
            @click="toggleNotification(item.key)"
          >
            {{ item.enabled ? '已开启' : '已关闭' }}
          </button>
        </div>
        <button class="btn-primary" @click="notificationsMutation.mutate()">保存通知设置</button>
      </div>
      <EmptyPanel v-else title="暂无通知配置" description="首次进入会自动创建默认通知设置。" />
    </AppCard>

    <AppCard title="对照与说明" subtitle="新 UI 的设置项已独立于 legacy 页面，不再回填旧模板。">
      <div class="space-y-4 text-sm text-slate-300">
        <div class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          用户名、密码、通知偏好都只作用于当前账号，不会影响其他用户的数据和会话。
        </div>
        <div class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          修改密码后，其他设备的 refresh token 会失效；如果需要立即清退当前设备，也可以直接使用“安全登出所有会话”。
        </div>
        <a href="/legacy" target="_blank" rel="noreferrer" class="inline-flex rounded-2xl border border-slate-700 px-4 py-2 text-sm text-indigo-300 hover:border-indigo-400 hover:text-indigo-200">
          打开 Legacy 页面做对照
        </a>
      </div>
    </AppCard>
  </div>
</template>
