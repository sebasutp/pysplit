import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api'
import { onlineRepository } from './online'
import { REPOSITORY_METHODS } from './contract'

/**
 * @param {unknown} body
 * @param {number} [status]
 * @param {Record<string, string>} [headers]
 */
function jsonResponse(body, status = 200, headers = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get: (/** @type {string} */ name) => {
        const key = name.toLowerCase()
        if (key === 'content-type') return headers['content-type'] || 'application/json'
        return headers[key] || null
      },
    },
    json: async () => body,
    text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
  api.clearAccessToken()
})

describe('repository contract', () => {
  it('exposes every documented method', () => {
    for (const path of REPOSITORY_METHODS) {
      const parts = path.split('.')
      let current = /** @type {Record<string, any>} */ (onlineRepository)
      for (const part of parts) {
        expect(current, `${path} is missing ${part}`).toBeTruthy()
        current = current[part]
      }
      expect(typeof current, `${path} must be a function`).toBe('function')
    }
  })

  it('passes group ids as a comma-separated filter', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 50, offset: 0 }))
    vi.stubGlobal('fetch', fetchMock)

    await onlineRepository.groups.list({ ids: ['g1', 'g2'] })

    expect(fetchMock.mock.calls[0][0]).toBe('/api/groups?ids=g1%2Cg2')
  })

  it('normalises currencyCode when creating a group', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ id: 'g1', name: 'Trip', participants: [] }, 201),
    )
    vi.stubGlobal('fetch', fetchMock)

    const group = await onlineRepository.groups.create({
      name: 'Trip',
      currencyCode: 'EUR',
      participants: [{ name: 'Ada' }],
    })

    expect(group.id).toBe('g1')
    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body.currency_code).toBe('EUR')
    expect(body.currencyCode).toBeUndefined()
  })

  it('returns null for a missing group', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: 'missing' }, 404)))

    await expect(onlineRepository.groups.get('missing')).resolves.toBeNull()
  })

  it('maps validation errors to RepositoryError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ detail: [{ msg: 'bad' }] }, 422)),
    )

    await expect(onlineRepository.groups.create({ name: '' })).rejects.toMatchObject({
      name: 'RepositoryError',
      code: 'validation',
      status: 422,
    })
  })

  it('normalises aborts', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new DOMException('aborted', 'AbortError')),
    )

    await expect(onlineRepository.groups.list({}, { signal: new AbortController().signal })).rejects.toMatchObject({
      name: 'RepositoryError',
      code: 'aborted',
    })
  })

  it('refreshes once and retries a 401', async () => {
    let groupCalls = 0
    const fetchMock = vi.fn(async (url) => {
      if (url.endsWith('/auth/refresh')) {
        return jsonResponse({ access_token: 'new-token', user: { id: 'u1' } })
      }
      if (url.endsWith('/groups')) {
        groupCalls += 1
        if (groupCalls === 1) return jsonResponse({ detail: 'expired' }, 401)
        return jsonResponse({ items: [], total: 0, limit: 50, offset: 0 })
      }
      throw new Error(`unexpected ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(onlineRepository.groups.list()).resolves.toMatchObject({ total: 0 })
    expect(groupCalls).toBe(2)
    expect(api.getAccessToken()).toBe('new-token')
  })

  it('returns null when there is no refresh session', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: 'no session' }, 401)))

    await expect(onlineRepository.auth.refresh()).resolves.toBeNull()
  })
})
