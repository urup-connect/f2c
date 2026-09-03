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
     * `siteConfig()` validates the deployment configuration on each call, so the unit suite
     * supplies it here rather than depending on a developer's .env.local. Deployed, these come
     * from the container app and the container refuses to start without them -- see
     * frontend/deploy/entrypoint.sh.
     *
     * Two variables, not four: the market reads no CDN_BASE_URL and no SUPPORT_EMAIL. See
     * lib/site.ts.
     */
    env: {
      APP_ENV: 'local',
      SITE_URL: 'http://localhost:3001',
    },
    setupFiles: ['./vitest.setup.ts'],
    // The routes, the components and the pure modules. There is no src/ directory.
    include: ['{app,components,lib}/**/*.{test,spec}.{ts,tsx}'],
    exclude: ['node_modules', '.next'],
    css: false,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['{app,components,lib}/**/*.{ts,tsx}'],
      exclude: ['**/*.{test,spec}.{ts,tsx}', 'app/**/layout.tsx'],
    },
  },
})
