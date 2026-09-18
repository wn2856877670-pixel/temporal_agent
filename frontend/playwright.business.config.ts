import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests', testMatch: 'business.spec.ts', timeout: 30000, workers: 1,
  use: { baseURL: 'http://127.0.0.1:5174', channel: 'msedge', screenshot: 'only-on-failure' },
  webServer: { command: 'node node_modules/vite/bin/vite.js --mode business --host 127.0.0.1 --port 5174 --strictPort', url: 'http://127.0.0.1:5174', reuseExistingServer: false },
});
