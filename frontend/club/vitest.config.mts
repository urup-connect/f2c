import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  resolve: {
    // Resolves the "@/*" aliases declared in tsconfig.json.
    tsconfigPaths: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    /*
     * lib/site.ts validates the deployment configuration when it is first loaded, so the
     * unit suite supplies it here rather than depending on a developer's .env.local.
     */
    env: {
      APP_ENV: 'local',
      SITE_URL: 'http://localhost:3000',
      CDN_BASE_URL: 'http://localhost:3000/static',
      SUPPORT_EMAIL: 'hello@example.invalid',
    },
    setupFiles: ['./vitest.setup.ts'],
    // The routes, the components and the pure modules. There is no src/ directory.
    include: ['{app,components,lib}/**/*.{test,spec}.{ts,tsx}'],
    exclude: ['node_modules', '.next', 'tests/e2e'],
    css: false,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['{app,components,lib}/**/*.{ts,tsx}'],
      exclude: ['**/*.{test,spec}.{ts,tsx}', 'app/**/layout.tsx'],
    },
  },
})
