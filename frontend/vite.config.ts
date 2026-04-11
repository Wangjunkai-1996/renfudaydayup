import { fileURLToPath, URL } from 'node:url';

import vue from '@vitejs/plugin-vue';
import { defineConfig, loadEnv } from 'vite';

function toWebSocketTarget(apiTarget: string): string {
  if (apiTarget.startsWith('https://')) {
    return apiTarget.replace('https://', 'wss://');
  }
  if (apiTarget.startsWith('http://')) {
    return apiTarget.replace('http://', 'ws://');
  }
  return apiTarget;
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const apiPort = env.RENFU_NEXT_API_PORT || '9000';
  const frontendPort = Number(env.RENFU_NEXT_FRONTEND_PORT || '5173');
  const apiTarget = env.RENFU_NEXT_API_TARGET || `http://127.0.0.1:${apiPort}`;

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      host: '0.0.0.0',
      port: frontendPort,
      proxy: {
        '/api': apiTarget,
        '/ws': toWebSocketTarget(apiTarget),
        '/legacy': apiTarget,
      },
    },
  };
});
