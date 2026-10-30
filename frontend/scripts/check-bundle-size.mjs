#!/usr/bin/env node
/**
 * Enforce the Stage 12 initial-JavaScript budget.
 *
 * The entry HTML lists the entry module and every modulepreload chunk that the
 * browser needs before the first route renders. Route pages are intentionally
 * lazy, so their chunks are not counted here. Sizes are measured after gzip,
 * which is what the web tier serves to modern browsers.
 */
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { gzipSync } from 'node:zlib'

const BUDGET_BYTES = Number(process.env.INITIAL_JS_BUDGET_BYTES || 300 * 1024)
const dist = resolve(process.cwd(), 'dist')
const indexPath = resolve(dist, 'index.html')

if (!existsSync(indexPath)) {
  console.error(`Missing ${indexPath}. Run "npm run build" first.`)
  process.exit(1)
}

const html = readFileSync(indexPath, 'utf8')
const pattern = /<(?:script[^>]+src|link[^>]+href)="([^"]+\.js)"/g
const assets = new Set()
let match
while ((match = pattern.exec(html))) {
  const asset = match[1].replace(/^\//, '')
  if (asset) assets.add(asset)
}

if (assets.size === 0) {
  console.error('No initial JavaScript assets found in dist/index.html')
  process.exit(1)
}

let total = 0
const rows = []
for (const asset of [...assets].sort()) {
  const path = resolve(dist, asset)
  if (!existsSync(path)) {
    console.error(`Referenced asset is missing from dist: ${asset}`)
    process.exit(1)
  }
  const gzip = gzipSync(readFileSync(path)).length
  total += gzip
  rows.push({ asset, gzipBytes: gzip })
}

for (const row of rows) {
  console.log(`${String(row.gzipBytes).padStart(8)} B  ${row.asset}`)
}
console.log(`\nInitial JavaScript: ${(total / 1024).toFixed(1)} KiB gzip (${total} bytes)`) 
console.log(`Budget:            ${(BUDGET_BYTES / 1024).toFixed(1)} KiB gzip (${BUDGET_BYTES} bytes)`)

if (total > BUDGET_BYTES) {
  console.error('FAIL: initial JavaScript exceeds the Stage 12 budget.')
  process.exit(1)
}
console.log('OK: initial JavaScript is within budget.')
