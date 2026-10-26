/**
 * PWA manifest and Workbox policy shared by the Vite build and unit tests.
 *
 * Keeping the values here (rather than inline in vite.config.js) means the
 * installability contract — start URL, display mode, icons, shortcuts and the
 * `/api` NetworkOnly rule — can be asserted without building the app.
 */

/** @type {Record<string, any>} */
export const manifest = {
  id: '/groups',
  name: 'pysplit — Split expenses with friends',
  short_name: 'pysplit',
  description:
    'Split expenses with friends and family. Works offline once a group has been synchronized.',
  lang: 'en',
  dir: 'ltr',
  start_url: '/groups',
  scope: '/',
  display: 'standalone',
  display_override: ['window-controls-overlay', 'standalone', 'minimal-ui'],
  orientation: 'portrait-primary',
  theme_color: '#0b7a5b',
  background_color: '#ffffff',
  categories: ['finance', 'productivity', 'utilities'],
  icons: [
    {
      src: '/icons/icon-192.png',
      sizes: '192x192',
      type: 'image/png',
      purpose: 'any',
    },
    {
      src: '/icons/icon-512.png',
      sizes: '512x512',
      type: 'image/png',
      purpose: 'any',
    },
    {
      src: '/icons/maskable-512.png',
      sizes: '512x512',
      type: 'image/png',
      purpose: 'maskable',
    },
  ],
  shortcuts: [
    {
      name: 'My groups',
      short_name: 'Groups',
      description: 'Open your recent groups',
      url: '/groups',
      icons: [{ src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' }],
    },
    {
      name: 'Create a group',
      short_name: 'Create',
      description: 'Start a new shared expense group',
      url: '/groups/create',
      icons: [{ src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' }],
    },
  ],
}

/** Files that are copied verbatim and must be available offline. */
export const includeAssets = [
  'favicon.png',
  'apple-touch-icon.png',
  'icons/*.png',
  'splash/*.png',
]

/**
 * Cache names are versioned. Bump CACHE_VERSION when the runtime caching
 * policy changes; `services/pwa.js` deletes older `pysplit-images-*` and
 * `pysplit-fonts-*` caches after the new worker takes control.
 */
export const CACHE_VERSION = 'v2'
export const CACHE_NAMES = {
  images: `pysplit-images-${CACHE_VERSION}`,
  fonts: `pysplit-fonts-${CACHE_VERSION}`,
}

/** @type {Record<string, any>} */
export const workbox = {
  // Never activate a new build behind the user's back: the update prompt asks
  // for an explicit reload (see services/pwa.js).
  skipWaiting: false,
  clientsClaim: false,
  cleanupOutdatedCaches: true,
  navigateFallback: '/index.html',
  // API requests must always reach the network. Besides the runtime route
  // below this also stops the navigation fallback from answering deep /api
  // URLs with the SPA shell.
  navigateFallbackDenylist: [/^\/api\//],
  globPatterns: [
    '**/*.{js,css,html,svg,png,ico,webmanifest,woff,woff2,ttf,otf}',
  ],
  globIgnores: ['**/sw.js', '**/workbox-*.js'],
  runtimeCaching: [
    {
      // Keep this first: an API image URL must never be served from a Workbox
      // cache, even though its path ends in an image extension.
      urlPattern: /\/api(?:\/|$)/,
      handler: 'NetworkOnly',
    },
    {
      urlPattern: /\.(?:png|jpg|jpeg|svg|gif|webp|avif|ico)$/i,
      handler: 'CacheFirst',
      options: {
        cacheName: CACHE_NAMES.images,
        expiration: {
          maxEntries: 100,
          maxAgeSeconds: 60 * 60 * 24 * 30,
        },
        cacheableResponse: { statuses: [0, 200] },
      },
    },
    {
      urlPattern: /\.(?:woff2?|ttf|otf)$/i,
      handler: 'CacheFirst',
      options: {
        cacheName: CACHE_NAMES.fonts,
        expiration: {
          maxEntries: 20,
          maxAgeSeconds: 60 * 60 * 24 * 365,
        },
        cacheableResponse: { statuses: [0, 200] },
      },
    },
  ],
}
