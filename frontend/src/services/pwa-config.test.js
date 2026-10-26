import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import {
  CACHE_NAMES,
  CACHE_VERSION,
  includeAssets,
  manifest,
  workbox,
} from '../../pwa.config.js'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..')

describe('PWA manifest', () => {
  it('is installable with the required start URL, mode and icons', () => {
    expect(manifest.start_url).toBe('/groups')
    expect(manifest.scope).toBe('/')
    expect(manifest.display).toBe('standalone')
    expect(manifest.name.length).toBeGreaterThan(3)
    expect(manifest.short_name.length).toBeLessThanOrEqual(12)
    expect(manifest.theme_color).toMatch(/^#[0-9a-f]{6}$/i)
    expect(manifest.background_color).toMatch(/^#[0-9a-f]{6}$/i)

    const sizes = manifest.icons.map((/** @type {any} */ icon) => icon.sizes)
    expect(sizes).toContain('192x192')
    expect(sizes).toContain('512x512')
    expect(
      manifest.icons.some((/** @type {any} */ icon) => icon.purpose === 'maskable'),
    ).toBe(true)

    expect(manifest.shortcuts.length).toBeGreaterThanOrEqual(2)
    expect(manifest.shortcuts.map((/** @type {any} */ shortcut) => shortcut.url)).toContain(
      '/groups',
    )

    for (const icon of manifest.icons) {
      expect(() => readFileSync(resolve(root, 'public', icon.src.slice(1)))).not.toThrow()
    }
  })

  it('ships an Apple touch icon and splash images', () => {
    expect(includeAssets).toContain('apple-touch-icon.png')
    expect(includeAssets).toContain('splash/*.png')
    const html = readFileSync(resolve(root, 'index.html'), 'utf8')
    expect(html).toContain('rel="apple-touch-icon"')
    expect(html).toContain('rel="apple-touch-startup-image"')
    expect(html).toContain('apple-mobile-web-app-capable')
  })
})

describe('Workbox policy', () => {
  it('precaches the shell, falls back to index.html and never caches /api', () => {
    expect(workbox.navigateFallback).toBe('/index.html')
    expect(workbox.navigateFallbackDenylist.some((/** @type {RegExp} */ rule) => rule.test('/api/groups'))).toBe(
      true,
    )
    expect(workbox.cleanupOutdatedCaches).toBe(true)
    expect(workbox.skipWaiting).toBe(false)
    expect(workbox.clientsClaim).toBe(false)
    expect(workbox.globPatterns.join(' ')).toContain('html')
    expect(workbox.globPatterns.join(' ')).toContain('js')
    expect(workbox.globPatterns.join(' ')).toContain('css')
    expect(workbox.globPatterns.join(' ')).toContain('webmanifest')

    const routes = workbox.runtimeCaching
    const api = routes[0]
    expect(api.handler).toBe('NetworkOnly')
    expect(api.urlPattern.test('/api/groups/g1/expenses')).toBe(true)
    // The API route must come before the image CacheFirst rule.
    expect(routes[1].handler).toBe('CacheFirst')
    expect(routes[1].options.cacheName).toBe(CACHE_NAMES.images)
    expect(routes[2].options.cacheName).toBe(CACHE_NAMES.fonts)
    expect(CACHE_NAMES.images).toContain(`-${CACHE_VERSION}`)
    expect(CACHE_NAMES.fonts).toContain(`-${CACHE_VERSION}`)
    // NetworkOnly ignores cacheName; keeping one would be misleading.
    expect(api.options?.cacheName).toBeUndefined()
  })
})
