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

/** @param {string} url */
function route(url) {
  if (url.endsWith('/auth/refresh')) return jsonResponse({ detail: 'no session' }, 401)
  if (url.endsWith('/auth/me')) {
    return jsonResponse({ user: null, providers: { google: false, github: false } })
  }
  if (url.endsWith('/groups/sync')) {
    return jsonResponse({ is_authenticated: false, groups: [], user_groups: [] })
  }
  return jsonResponse({ items: [], total: 0, limit: 50, offset: 0 })
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url) => Promise.resolve(route(String(url)))))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('App shell', () => {
  it('renders the groups route and the empty recent state', async () => {
    render(
      <MemoryRouter initialEntries={['/groups']}>
        <App />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: 'My groups' })).toBeInTheDocument()
    expect(
      await screen.findByText('You have not visited any group recently.'),
    ).toBeInTheDocument()
  })

  it('redirects / to /groups', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: 'My groups' })).toBeInTheDocument()
  })

  it('requires sign-in on the create group page', async () => {
    render(
      <MemoryRouter initialEntries={['/groups/create']}>
        <App />
      </MemoryRouter>,
    )

    expect(await screen.findByText('Authentication Required')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign in to Create Group' })).toBeInTheDocument()
  })
})
