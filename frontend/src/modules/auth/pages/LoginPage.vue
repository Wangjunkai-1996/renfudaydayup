<script setup lang="ts">
import { reactive, ref } from 'vue';
import { useRouter } from 'vue-router';

import { useAuthStore } from '@/shared/stores/auth';

const authStore = useAuthStore();
const router = useRouter();
const form = reactive({ username: 'legacy_admin', password: 'ChangeMe123!' });
const error = ref('');

async function submit() {
  error.value = '';
  try {
    await authStore.login(form);
    await router.push('/dashboard');
  } catch (err) {
    error.value = err instanceof Error ? err.message : '登录失败';
  }
}
</script>

<template>
  <div class="flex min-h-screen items-center justify-center px-4">
    <div class="glass-card w-full max-w-md p-8">
      <div class="text-xs uppercase tracking-[0.3em] text-indigo-300">Renfu Next</div>
      <h1 class="mt-4 text-3xl font-bold text-white">欢迎回来</h1>
      <p class="mt-2 text-sm text-slate-400">登录后查看你自己的股票、策略、信号和模拟交易账户。</p>

      <form class="mt-8 space-y-4" @submit.prevent="submit">
        <label class="block">
          <span class="mb-2 block text-sm text-slate-300">用户名</span>
          <input v-model="form.username" class="w-full rounded-2xl border border-slate-700 bg-slate-950/70 px-4 py-3 text-white outline-none focus:border-indigo-400" />
        </label>
        <label class="block">
          <span class="mb-2 block text-sm text-slate-300">密码</span>
          <input v-model="form.password" type="password" class="w-full rounded-2xl border border-slate-700 bg-slate-950/70 px-4 py-3 text-white outline-none focus:border-indigo-400" />
        </label>
        <p v-if="error" class="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{{ error }}</p>
        <button class="w-full rounded-2xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white hover:bg-indigo-500" :disabled="authStore.loading">
          {{ authStore.loading ? '登录中...' : '登录' }}
        </button>
      </form>
    </div>
  </div>
</template>
