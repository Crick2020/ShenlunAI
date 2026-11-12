import path from 'path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
// @ts-ignore - 纯 Node ESM 脚本，无 .d.ts 声明
import { dailyPrerender } from './scripts/prerender-daily.mjs';

export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, '.', '');
    // 部署到 Gitee Pages 子路径时设置 VITE_BASE_URL，如 /ShenlunAI-Pages/
    const base = process.env.VITE_BASE_URL || env.VITE_BASE_URL || '/';
    return {
      base,
      server: {
        port: 3000,
        host: '0.0.0.0',
      },
      plugins: [react(), dailyPrerender() as any],
      define: {
        'process.env.API_KEY': JSON.stringify(env.GEMINI_API_KEY),
        'process.env.GEMINI_API_KEY': JSON.stringify(env.GEMINI_API_KEY)
      },
      resolve: {
        alias: {
          '@': path.resolve(__dirname, '.'),
        }
      }
    };
});
