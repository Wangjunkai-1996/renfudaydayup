import { fileURLToPath, URL } from 'node:url';

import vue from '@vitejs/plugin-vue';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    pool: 'forks',
    maxWorkers: 2,
    minWorkers: 1,
    maxConcurrency: 2,
    testTimeout: 15000,
    hookTimeout: 15000,
    teardownTimeout: 5000,
    exclude: ['e2e/**', 'node_modules/**'],
  },
});
