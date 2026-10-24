import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'

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

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ status: 'ok', version: '0.1.0' })))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('App shell', () => {
  it('renders the groups route and reports API health', async () => {
    render(
      <MemoryRouter initialEntries={['/groups']}>
        <App />
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { name: 'Groups' })).toBeInTheDocument()
    expect(await screen.findByText('API ok')).toBeInTheDocument()
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      '/api/health',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('redirects / to /groups', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: 'Groups' })).toBeInTheDocument()
  })

  it('shows an offline indicator when the health request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))

    render(
      <MemoryRouter initialEntries={['/groups']}>
        <App />
      </MemoryRouter>,
    )

    expect(await screen.findByText('API offline')).toBeInTheDocument()
  })
})
