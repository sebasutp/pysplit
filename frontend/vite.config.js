import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The SPA always calls same-origin /api. Vite proxies it to the API in
// development; nginx proxies it in production. No CORS is needed either way.
const apiTarget = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000'

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
    changeOrigin: true,
  },
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
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
    setupFiles: ['./src/test/setup.js'],
    css: true,
    restoreMocks: true,
  },
})
