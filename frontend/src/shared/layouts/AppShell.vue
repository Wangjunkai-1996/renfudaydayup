<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';

import { useAuthStore } from '@/shared/stores/auth';
import { useRealtimeStore } from '@/shared/stores/realtime';

const authStore = useAuthStore();
const realtimeStore = useRealtimeStore();
const route = useRoute();
const router = useRouter();

const navigation = computed(() => {
  const items = [
    { to: '/dashboard', label: 'Dashboard' },
    { to: '/market', label: 'Market' },
    { to: '/signals', label: 'Signals' },
    { to: '/paper', label: 'Paper' },
    { to: '/reports', label: 'Reports' },
    { to: '/diagnostics', label: 'Diagnostics' },
    { to: '/strategy', label: 'Strategy' },
    { to: '/watchlist', label: 'Watchlist' },
    { to: '/settings', label: 'Settings' },
  ];
  if (authStore.user?.role === 'admin') {
    items.push({ to: '/admin', label: 'Admin' });
  }
  return items;
});


onMounted(() => {
  if (authStore.user) {
    realtimeStore.connect();
  }
});

onUnmounted(() => {
  realtimeStore.disconnect();
});

watch(
  () => authStore.user?.id,
  (userId) => {
    if (userId) {
      realtimeStore.connect();
    } else {
      realtimeStore.disconnect();
    }
  },
  { immediate: true },
);
async function logout() {
  await authStore.logout();
  await router.push('/login');
}
</script>

<template>
  <div class="min-h-screen px-4 py-4 lg:px-6">
    <div class="mx-auto grid max-w-[1800px] gap-4 xl:grid-cols-[260px_minmax(0,1fr)]">
      <aside class="glass-card flex flex-col p-4">
        <div>
          <div class="text-xs uppercase tracking-[0.3em] text-indigo-300">Renfu Next</div>
          <div class="mt-2 text-2xl font-bold text-white">量化交易工作台</div>
          <p class="mt-2 text-sm text-slate-400">前后端分离、多用户隔离、实时数据驱动。</p>
        </div>
        <nav class="mt-6 flex flex-1 flex-col gap-2">
          <RouterLink
            v-for="item in navigation"
            :key="item.to"
            :to="item.to"
            class="rounded-2xl px-4 py-3 text-sm font-medium transition"
            :class="route.path === item.to ? 'bg-indigo-500/20 text-indigo-100' : 'text-slate-300 hover:bg-slate-800/80 hover:text-white'"
          >
            {{ item.label }}
          </RouterLink>
        </nav>
        <div class="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          <div class="text-sm font-medium text-white">{{ authStore.user?.username || '未登录' }}</div>
          <div class="mt-1 text-xs uppercase tracking-[0.24em] text-slate-500">{{ authStore.user?.role || 'guest' }}</div>
          <div class="mt-3 flex items-center gap-2 text-xs">
            <span class="inline-flex h-2.5 w-2.5 rounded-full" :class="realtimeStore.connected ? 'bg-emerald-400' : 'bg-slate-500'"></span>
            <span class="text-slate-400">实时流 {{ realtimeStore.connected ? '已连接' : '未连接' }}</span>
          </div>
          <div class="mt-2 text-xs text-slate-500">系统状态：{{ realtimeStore.systemStatus }}</div>
          <button class="mt-4 w-full rounded-2xl bg-slate-800 px-4 py-2 text-sm text-slate-100 hover:bg-slate-700" @click="logout">
            退出登录
          </button>
        </div>
      </aside>
      <main class="min-w-0">
        <slot />
      </main>
    </div>
  </div>
</template>
