import {defineConfig} from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [
    ['line'],
    ['junit', {outputFile: '/evidence/junit-ui.xml'}],
  ],
  outputDir: '/evidence/ui-artifacts',
  use: {
    baseURL: process.env.BASE_URL ?? 'http://frontend:3000',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
});
