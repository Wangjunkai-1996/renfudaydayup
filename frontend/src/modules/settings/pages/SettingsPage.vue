<script setup lang="ts">
import { useAuthStore } from '@/shared/stores/auth';
import AppCard from '@/shared/ui/AppCard.vue';
import PageHeader from '@/shared/ui/PageHeader.vue';

const authStore = useAuthStore();
</script>

<template>
  <PageHeader title="Settings" subtitle="账户与通知设置的占位页，后续继续细化。" />
  <div class="grid gap-4 xl:grid-cols-2">
    <AppCard title="Account Settings">
      <div class="space-y-2 text-sm text-slate-300">
        <div>用户名：{{ authStore.user?.username }}</div>
        <div>角色：{{ authStore.user?.role }}</div>
        <div>后续将在这里补充密码修改、通知配置与偏好设置。</div>
      </div>
    </AppCard>
    <AppCard title="Legacy Bridge">
      <a href="/legacy" target="_blank" class="text-sm text-indigo-300 hover:text-indigo-200">打开 legacy 页面核对新旧行为</a>
    </AppCard>
  </div>
</template>
