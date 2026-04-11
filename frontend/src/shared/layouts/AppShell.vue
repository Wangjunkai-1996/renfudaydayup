<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';

import StateBadge from '@/shared/ui/StateBadge.vue';
import { useAuthStore } from '@/shared/stores/auth';
import { useRealtimeStore } from '@/shared/stores/realtime';

const authStore = useAuthStore();
const realtimeStore = useRealtimeStore();
const route = useRoute();
const router = useRouter();

const navigation = computed(() => {
  const items = [
    { to: '/dashboard', label: '总览' },
    { to: '/market', label: '盯盘工作区' },
    { to: '/signals', label: '信号中心' },
    { to: '/paper', label: '模拟账户' },
    { to: '/reports', label: '报告中心' },
    { to: '/diagnostics', label: '诊断调优' },
    { to: '/strategy', label: '策略参数' },
    { to: '/watchlist', label: '自选管理' },
    { to: '/settings', label: '账户设置' },
  ];
  if (authStore.user?.role === 'admin') {
    items.push({ to: '/admin', label: '管理后台' });
  }
  return items;
});

const connectionTone = computed(() => (realtimeStore.connected ? 'positive' : realtimeStore.connecting ? 'warning' : 'negative'));
const tradingTone = computed(() => (realtimeStore.isTrading ? 'positive' : 'warning'));

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
    <div class="mx-auto grid max-w-[1800px] gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
      <aside class="glass-card flex flex-col p-4">
        <div>
          <div class="text-xs uppercase tracking-[0.3em] text-indigo-300">Renfu Next</div>
          <div class="mt-2 text-2xl font-bold text-white">量化交易工作台</div>
          <p class="mt-2 text-sm text-slate-400">前后端分离、多用户隔离、真实 Legacy 桥接。</p>
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
          <div class="mt-4 flex flex-wrap gap-2">
            <StateBadge :label="realtimeStore.connected ? '实时流在线' : realtimeStore.connecting ? '实时流连接中' : '实时流离线'" :tone="connectionTone" />
            <StateBadge :label="realtimeStore.isTrading ? '交易时段' : '非交易时段'" :tone="tradingTone" />
            <StateBadge :label="realtimeStore.legacyMode ? 'Legacy 真数据' : 'Next 模式'" :tone="realtimeStore.legacyMode ? 'brand' : 'default'" />
          </div>
          <div class="mt-3 text-xs text-slate-500">系统状态：{{ realtimeStore.systemStatus }}<span v-if="realtimeStore.lastEventAt"> · 最近事件 {{ realtimeStore.lastEventAt }}</span></div>
          <div class="mt-4 flex gap-2">
            <a class="btn-secondary flex-1 text-center" href="/legacy" target="_blank" rel="noreferrer">打开 Legacy</a>
            <button class="btn-secondary flex-1" @click="logout">退出登录</button>
          </div>
        </div>
      </aside>
      <main class="min-w-0">
        <div class="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-3xl border border-slate-800 bg-slate-950/60 px-5 py-4">
          <div>
            <div class="text-sm text-slate-300">当前页面：{{ navigation.find((item) => item.to === route.path)?.label || '工作台' }}</div>
            <div class="mt-1 text-xs text-slate-500">新 UI 已切到中文业务态展示，不再显示原始 JSON 占位块。</div>
          </div>
          <div class="flex flex-wrap gap-2">
            <StateBadge :label="authStore.user?.role === 'admin' ? '管理员会话' : '用户会话'" tone="brand" />
            <StateBadge :label="realtimeStore.watchlistQuotes.length ? `自选报价 ${realtimeStore.watchlistQuotes.length}` : '自选报价待同步'" :tone="realtimeStore.watchlistQuotes.length ? 'positive' : 'warning'" />
            <StateBadge :label="realtimeStore.signals.length ? `信号 ${realtimeStore.signals.length}` : '暂无实时信号'" :tone="realtimeStore.signals.length ? 'positive' : 'default'" />
          </div>
        </div>
        <slot />
      </main>
    </div>
  </div>
</template>
