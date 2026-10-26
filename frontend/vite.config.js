import { mkdirSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

import { includeAssets, manifest, workbox } from './pwa.config.js'
import { DATABASE_BUILD_CONTRACT } from './src/services/db-schema.js'

// The SPA calls /api by default and Vite proxies it to the API. When
// VITE_API_BASE_URL is an absolute URL the browser calls that origin directly
// and this proxy is unused. No CORS is needed for the proxy setup.
const apiTarget = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000'

// Keep the browser-facing Host header by default so the backend builds OAuth
// redirect URIs and cookies for the domain the user opened, even when no
// BASE_URL is configured. Set VITE_API_PROXY_CHANGE_ORIGIN=true when the
// target is a virtual-hosted remote API that needs its own Host header.
const proxyChangeOrigin = process.env.VITE_API_PROXY_CHANGE_ORIGIN === 'true'

// Local HTTPS targets often use a self-signed certificate. Prefer a trusted
// certificate; set VITE_API_PROXY_SECURE=false only for local development.
const proxySecure = process.env.VITE_API_PROXY_SECURE !== 'false'

// Public hostname clients use (e.g. a Tailscale MagicDNS name). It is added to
// allowedHosts; without that Vite rejects non-localhost Host headers with 403
// "Blocked request".
const webHost = process.env.WEB_HOST || '127.0.0.1'
const webPort = Number(process.env.WEB_PORT || 5173)

// Bind all interfaces for a public hostname so the name does not need to be
// locally resolvable and both loopback and Tailscale/LAN addresses work.
const loopbackHosts = new Set(['127.0.0.1', 'localhost', '::1'])
const listenHost = loopbackHosts.has(webHost) ? '127.0.0.1' : true

const proxy = {
  '/api': {
    target: apiTarget,
    changeOrigin: proxyChangeOrigin,
    secure: proxySecure,
  },
}

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      // Registration is manual so the update prompt controls when a waiting
      // worker activates. `registerType: 'prompt'` never calls skipWaiting on
      // its own.
      registerType: 'prompt',
      injectRegister: false,
      includeAssets,
      manifest,
      manifestFilename: 'manifest.webmanifest',
      workbox,
      devOptions: { enabled: false },
    }),
    {
      // Emit the waiting build's Dexie contract next to the app shell. It is
      // intentionally not precached: `fetchIncomingBuildContract()` fetches it
      // with `cache: 'no-store'` so an update can be checked before activation.
      name: 'pwa-build-contract',
      apply: 'build',
      closeBundle() {
        const output = fileURLToPath(new URL('./dist', import.meta.url))
        mkdirSync(output, { recursive: true })
        writeFileSync(
          fileURLToPath(new URL('./dist/pwa-build.json', import.meta.url)),
          JSON.stringify(
            {
              ...DATABASE_BUILD_CONTRACT,
              buildId: process.env.PWA_BUILD_ID || process.env.npm_package_version || 'dev',
            },
            null,
            2,
          ),
        )
      },
    },
  ],
  server: {
    host: listenHost,
    port: webPort,
    strictPort: true,
    allowedHosts: [webHost],
    proxy,
  },
  preview: {
    host: listenHost,
    port: 4173,
    strictPort: true,
    allowedHosts: [webHost],
    proxy,
  },
  build: {
    sourcemap: false,
    target: 'es2022',
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.{test,spec}.{js,jsx,ts,tsx}'],
    setupFiles: ['./src/test/setup.js'],
    css: true,
    restoreMocks: true,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      include: ['src/**/*.{js,jsx,ts,tsx}'],
      // Conservative floors measured from the current suite, set a few points
      // below the actual totals so the gate catches regressions without
      // failing on minor coverage shifts.
      thresholds: {
        statements: 29,
        branches: 25,
        functions: 22,
        lines: 30,
      },
    },
  },
})
