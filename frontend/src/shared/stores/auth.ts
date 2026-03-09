import { defineStore } from 'pinia';

import { apiClient } from '@/shared/api/client';
import type { User } from '@/shared/api/types';

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as User | null,
    loading: false,
    bootstrapped: false,
  }),
  actions: {
    async bootstrap() {
      if (this.bootstrapped) {
        return;
      }
      try {
        this.user = await apiClient.get<User>('/api/v1/me');
      } catch {
        this.user = null;
      } finally {
        this.bootstrapped = true;
      }
    },
    async login(payload: { username: string; password: string }) {
      this.loading = true;
      try {
        const session = await apiClient.post<{ user: User }>('/api/v1/auth/login', payload);
        this.user = session.user;
        this.bootstrapped = true;
      } finally {
        this.loading = false;
      }
    },
    async logout() {
      await apiClient.post('/api/v1/auth/logout');
      this.user = null;
      this.bootstrapped = true;
    },
  },
});
