import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, api } from './api'

/**
 * @param {unknown} body
 * @param {number} [status]
 */
function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => 'application/json' },
    json: async () => body,
    text: async () => JSON.stringify(body),
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('api client', () => {
  it('prefixes /api and parses JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: 'ok' }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.get('/health')).resolves.toEqual({ status: 'ok' })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/health',
      expect.objectContaining({ method: 'GET', credentials: 'same-origin' }),
    )
  })

  it('serialises JSON bodies', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 'g1' }, 201))
    vi.stubGlobal('fetch', fetchMock)

    await api.post('/groups', { body: { name: 'Trip' } })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/groups',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ name: 'Trip' }),
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    )
  })

  it('maps HTTP errors to RepositoryError-compatible codes', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: 'missing' }, 404)))

    await expect(api.get('/missing')).rejects.toMatchObject({
      name: 'ApiError',
      code: 'not_found',
      status: 404,
      detail: 'missing',
    })
  })

  it('maps network failures to a retryable network error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))

    await expect(api.get('/health')).rejects.toMatchObject({
      code: 'network',
      retryable: true,
    })
  })

  it('normalises aborts', async () => {
    const abort = new DOMException('aborted', 'AbortError')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abort))

    const error = await api.get('/health').catch((caught) => caught)
    expect(error).toBeInstanceOf(ApiError)
    expect(/** @type {ApiError} */ (error).code).toBe('aborted')
  })

  it('returns undefined for 204 responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 204,
        headers: { get: () => null },
      }),
    )

    await expect(api.delete('/groups/g1')).resolves.toBeUndefined()
  })
})
