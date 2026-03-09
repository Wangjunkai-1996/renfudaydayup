import { createRouter, createWebHistory } from 'vue-router';

import { useAuthStore } from '@/shared/stores/auth';

const LoginPage = () => import('@/modules/auth/pages/LoginPage.vue');
const AdminPage = () => import('@/modules/admin/pages/AdminPage.vue');
const DashboardPage = () => import('@/modules/dashboard/pages/DashboardPage.vue');
const DiagnosticsPage = () => import('@/modules/diagnostics/pages/DiagnosticsPage.vue');
const MarketPage = () => import('@/modules/market/pages/MarketPage.vue');
const PaperPage = () => import('@/modules/paper/pages/PaperPage.vue');
const ReportsPage = () => import('@/modules/reports/pages/ReportsPage.vue');
const SettingsPage = () => import('@/modules/settings/pages/SettingsPage.vue');
const SignalsPage = () => import('@/modules/signals/pages/SignalsPage.vue');
const StrategyPage = () => import('@/modules/strategy/pages/StrategyPage.vue');
const WatchlistPage = () => import('@/modules/watchlist/pages/WatchlistPage.vue');

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: LoginPage, meta: { public: true } },
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', component: DashboardPage },
    { path: '/signals', component: SignalsPage },
    { path: '/paper', component: PaperPage },
    { path: '/reports', component: ReportsPage },
    { path: '/diagnostics', component: DiagnosticsPage },
    { path: '/strategy', component: StrategyPage },
    { path: '/watchlist', component: WatchlistPage },
    { path: '/market', component: MarketPage },
    { path: '/settings', component: SettingsPage },
    { path: '/admin', component: AdminPage, meta: { requiresAdmin: true } },
  ],
});

router.beforeEach(async (to) => {
  const authStore = useAuthStore();
  if (!authStore.bootstrapped) {
    await authStore.bootstrap();
  }
  if (to.meta.public) {
    return true;
  }
  if (!authStore.user) {
    return '/login';
  }
  if (to.meta.requiresAdmin && authStore.user.role !== 'admin') {
    return '/dashboard';
  }
  return true;
});

export default router;
