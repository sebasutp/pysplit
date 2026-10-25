/**
 * Online repository: a thin pass-through over the one HTTP client.
 *
 * M1 uses this implementation. It must satisfy docs/repository-contract.md;
 * Stage 9A adds the Dexie implementation with the same method surface.
 */

import { api } from '../api'
import { API_BASE_URL } from '../config'
import { run } from './contract'

/** @typedef {{ signal?: AbortSignal }} ReadOptions */

/** @type {{google: boolean, github: boolean}} */
let providersCache = { google: false, github: false }

/**
 * @param {Record<string, string | number | boolean | undefined | null | string[]>} params
 * @returns {string}
 */
function query(params) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue
    if (Array.isArray(value)) {
      if (value.length) search.set(key, value.join(','))
      continue
    }
    if (value === '') continue
    search.set(key, String(value))
  }
  const encoded = search.toString()
  return encoded ? `?${encoded}` : ''
}

/**
 * @param {string} groupId
 * @returns {string}
 */
function groupPath(groupId) {
  return `/groups/${encodeURIComponent(groupId)}`
}

/**
 * OAuth entry point on the configured API origin.
 *
 * @param {'google'|'github'} provider
 * @param {string} [returnTo]
 * @returns {string}
 */
export function oauthStartUrl(provider, returnTo = '/groups') {
  return `${API_BASE_URL}/auth/oauth/${provider}/start?return_to=${encodeURIComponent(returnTo)}`
}

const auth = {
  /**
   * @param {ReadOptions} [options]
   * @returns {Promise<any | null>}
   */
  async me(options = {}) {
    return run(async () => {
      const payload = /** @type {any} */ (await api.get('/auth/me', { signal: options.signal }))
      if (payload) providersCache = payload.providers || providersCache
      return payload?.user ?? null
    })
  },
  /**
   * @param {ReadOptions} [options]
   * @returns {Promise<{access_token: string, user: any} | null>}
   */
  async refresh(options = {}) {
    return run(async () => {
      const payload = await api.refreshSession({ signal: options.signal })
      return payload
    })
  },
  /**
   * @param {ReadOptions} [options]
   * @returns {Promise<void>}
   */
  async logout(options = {}) {
    await run(async () => {
      await api.post('/auth/logout', {
        signal: options.signal,
        retryAuth: false,
        csrf: true,
      })
    })
    api.clearAccessToken()
    api.clearCsrfToken()
  },
  /**
   * @param {'google'|'github'} provider
   * @param {string} [returnTo]
   * @returns {void}
   */
  startOAuth(provider, returnTo = '/groups') {
    // Use the configured API origin so a split frontend/backend dev setup
    // lands on the backend instead of the static frontend dev server.
    window.location.assign(oauthStartUrl(provider, returnTo))
  },
  /** @returns {{google: boolean, github: boolean}} */
  providers() {
    return { ...providersCache }
  },
}

const groups = {
  /**
   * @param {{ids?: string[], status?: string}} [options]
   * @param {ReadOptions} [read]
   * @returns {Promise<any>}
   */
  async list(options = {}, read = {}) {
    return run(async () =>
      api.get(
        `/groups${query({ ids: options.ids, status: options.status })}`,
        { signal: read.signal },
      ),
    )
  },
  /**
   * @param {string} groupId
   * @param {ReadOptions} [options]
   * @returns {Promise<any | null>}
   */
  async get(groupId, options = {}) {
    return run(async () => {
      try {
        return await api.get(groupPath(groupId), { signal: options.signal })
      } catch (error) {
        if (
          error &&
          typeof error === 'object' &&
          'code' in error &&
          /** @type {{code?: unknown}} */ (error).code === 'not_found'
        ) {
          return null
        }
        throw error
      }
    })
  },
  /**
   * @param {string} groupId
   * @param {ReadOptions} [options]
   * @returns {Promise<any>}
   */
  async details(groupId, options = {}) {
    return run(async () => api.get(`${groupPath(groupId)}/details`, { signal: options.signal }))
  },
  /**
   * @param {any} input
   * @param {ReadOptions} [options]
   * @returns {Promise<any>}
   */
  async create(input, options = {}) {
    return run(async () => api.post('/groups', { body: normaliseGroupInput(input), signal: options.signal }))
  },
  /**
   * @param {string} groupId
   * @param {any} input
   * @param {ReadOptions} [options]
   * @returns {Promise<any>}
   */
  async update(groupId, input, options = {}) {
    return run(async () =>
      api.patch(groupPath(groupId), { body: normaliseGroupInput(input), signal: options.signal }),
    )
  },
  /**
   * @param {string} groupId
   * @param {ReadOptions} [options]
   * @returns {Promise<void>}
   */
  async removeMembership(groupId, options = {}) {
    await run(async () => api.delete(`${groupPath(groupId)}/membership`, { signal: options.signal }))
  },
  /**
   * @param {string} groupId
   * @param {ReadOptions} [options]
   * @returns {Promise<void>}
   */
  async recordAccess(groupId, options = {}) {
    await run(async () => api.post(`${groupPath(groupId)}/access`, { signal: options.signal }))
  },
  /**
   * @param {string} groupId
   * @param {boolean} value
   * @param {ReadOptions} [options]
   * @returns {Promise<any>}
   */
  async setStarred(groupId, value, options = {}) {
    return run(async () =>
      api.patch(`${groupPath(groupId)}/membership`, {
        body: { is_starred: value },
        signal: options.signal,
      }),
    )
  },
  /**
   * @param {string} groupId
   * @param {boolean} value
   * @param {ReadOptions} [options]
   * @returns {Promise<any>}
   */
  async setArchived(groupId, value, options = {}) {
    return run(async () =>
      api.patch(`${groupPath(groupId)}/membership`, {
        body: { is_archived: value },
        signal: options.signal,
      }),
    )
  },
  /**
   * @param {{groupIds?: string[], starredGroupIds?: string[], archivedGroupIds?: string[]}} [input]
   * @param {ReadOptions} [options]
   * @returns {Promise<any>}
   */
  async sync(input = {}, options = {}) {
    return run(async () =>
      api.post('/groups/sync', {
        body: {
          group_ids: input.groupIds || [],
          starred_group_ids: input.starredGroupIds || [],
          archived_group_ids: input.archivedGroupIds || [],
        },
        signal: options.signal,
      }),
    )
  },
}

const participants = {
  /**
   * @param {string} groupId
   * @param {ReadOptions} [options]
   * @returns {Promise<any[]>}
   */
  async list(groupId, options = {}) {
    return run(async () =>
      /** @type {any[]} */ (
        await api.get(`${groupPath(groupId)}/participants`, { signal: options.signal })
      ),
    )
  },
  /**
   * @param {string} groupId
   * @param {any} input
   * @param {ReadOptions} [options]
   * @returns {Promise<any>}
   */
  async upsert(groupId, input, options = {}) {
    return run(async () => {
      if (input?.id) {
        return api.patch(`${groupPath(groupId)}/participants/${encodeURIComponent(input.id)}`, {
          body: { name: input.name },
          signal: options.signal,
        })
      }
      return api.post(`${groupPath(groupId)}/participants`, {
        body: { name: input?.name },
        signal: options.signal,
      })
    })
  },
  /**
   * @param {string} groupId
   * @param {string} id
   * @param {ReadOptions} [options]
   * @returns {Promise<void>}
   */
  async remove(groupId, id, options = {}) {
    await run(async () =>
      api.delete(`${groupPath(groupId)}/participants/${encodeURIComponent(id)}`, {
        signal: options.signal,
      }),
    )
  },
}

const categories = {
  /**
   * @param {ReadOptions} [options]
   * @returns {Promise<any>}
   */
  async list(options = {}) {
    return run(async () => api.get('/categories', { signal: options.signal }))
  },
  /**
   * @param {string} title
   * @param {ReadOptions} [options]
   * @returns {Promise<{category_id: number}>}
   */
  async infer(title, options = {}) {
    return run(async () =>
      /** @type {{category_id: number}} */ (
        await api.post('/categories/infer', { body: { title }, signal: options.signal })
      ),
    )
  },
}

const expenses = {
  /**
   * @param {string} groupId
   * @param {any} [options]
   * @param {ReadOptions} [read]
   * @returns {Promise<any>}
   */
  async list(groupId, options = {}, read = {}) {
    return run(async () =>
      api.get(
        `${groupPath(groupId)}/expenses${query({
          limit: options.limit,
          offset: options.offset,
          from: options.from,
          to: options.to,
          q: options.q,
        })}`,
        { signal: read.signal || options.signal },
      ),
    )
  },
  /**
   * @param {string} groupId
   * @param {string} expenseId
   * @param {ReadOptions} [options]
   * @returns {Promise<any | null>}
   */
  async get(groupId, expenseId, options = {}) {
    return run(async () => {
      try {
        return await api.get(
          `${groupPath(groupId)}/expenses/${encodeURIComponent(expenseId)}`,
          { signal: options.signal },
        )
      } catch (error) {
        if (
          error &&
          typeof error === 'object' &&
          'code' in error &&
          /** @type {{code?: unknown}} */ (error).code === 'not_found'
        ) {
          return null
        }
        throw error
      }
    })
  },
  /**
   * @param {string} groupId
   * @param {any} input
   * @param {ReadOptions} [options]
   * @returns {Promise<any>}
   */
  async create(groupId, input, options = {}) {
    return run(async () =>
      api.post(`${groupPath(groupId)}/expenses`, { body: input, signal: options.signal }),
    )
  },
  /**
   * @param {string} groupId
   * @param {string} expenseId
   * @param {any} input
   * @param {ReadOptions} [options]
   * @returns {Promise<any>}
   */
  async update(groupId, expenseId, input, options = {}) {
    return run(async () =>
      api.patch(`${groupPath(groupId)}/expenses/${encodeURIComponent(expenseId)}`, {
        body: input,
        signal: options.signal,
      }),
    )
  },
  /**
   * @param {string} groupId
   * @param {string} expenseId
   * @param {ReadOptions} [options]
   * @returns {Promise<void>}
   */
  async remove(groupId, expenseId, options = {}) {
    await run(async () =>
      api.delete(`${groupPath(groupId)}/expenses/${encodeURIComponent(expenseId)}`, {
        signal: options.signal,
      }),
    )
  },
}

const balances = {
  /**
   * @param {string} groupId
   * @param {ReadOptions} [options]
   * @returns {Promise<any>}
   */
  async list(groupId, options = {}) {
    return run(async () => api.get(`${groupPath(groupId)}/balances`, { signal: options.signal }))
  },
  /**
   * @param {{group_id: string, participant_id: string}[]} entries
   * @param {ReadOptions} [options]
   * @returns {Promise<any[]>}
   */
  async forUser(entries, options = {}) {
    return run(async () => {
      if (!entries.length) return []
      const tokens = entries.map((entry) => `${entry.group_id}:${entry.participant_id}`)
      const payload = /** @type {any} */ (
        await api.get(`/balances${query({ groups: tokens })}`, { signal: options.signal })
      )
      return payload?.items ?? []
    })
  },
}

const stats = {
  /**
   * @param {string} groupId
   * @param {any} [options]
   * @param {ReadOptions} [read]
   * @returns {Promise<any>}
   */
  async overview(groupId, options = {}, read = {}) {
    return run(async () =>
      api.get(
        `${groupPath(groupId)}/stats${query({
          participant_id: options.participant_id,
          from: options.from,
          to: options.to,
        })}`,
        { signal: read.signal || options.signal },
      ),
    )
  },
  /**
   * @param {string} groupId
   * @param {number} categoryId
   * @param {any} [options]
   * @param {ReadOptions} [read]
   * @returns {Promise<any>}
   */
  async categoryExpenses(groupId, categoryId, options = {}, read = {}) {
    return run(async () =>
      api.get(
        `${groupPath(groupId)}/stats/categories/${categoryId}/expenses${query({
          from: options.from,
          to: options.to,
        })}`,
        { signal: read.signal || options.signal },
      ),
    )
  },
  /**
   * @param {string} groupId
   * @param {string} month
   * @param {any} [options]
   * @param {ReadOptions} [read]
   * @returns {Promise<any>}
   */
  async monthExpenses(groupId, month, options = {}, read = {}) {
    return run(async () =>
      api.get(
        `${groupPath(groupId)}/stats/months/${month}/expenses${query({
          from: options.from,
          to: options.to,
        })}`,
        { signal: read.signal || options.signal },
      ),
    )
  },
}

const activities = {
  /**
   * @param {string} groupId
   * @param {any} [options]
   * @param {ReadOptions} [read]
   * @returns {Promise<any>}
   */
  async list(groupId, options = {}, read = {}) {
    return run(async () =>
      api.get(
        `${groupPath(groupId)}/activities${query({
          cursor: options.cursor,
          limit: options.limit,
        })}`,
        { signal: read.signal || options.signal },
      ),
    )
  },
}

const receipts = {
  /**
   * @param {string} groupId
   * @param {{receipt_id?: string, expense_id?: string}} [options]
   * @param {ReadOptions} [read]
   * @returns {Promise<any | null>}
   */
  async get(groupId, options = {}, read = {}) {
    return run(async () => {
      const path = options.receipt_id
        ? `${groupPath(groupId)}/receipts/${encodeURIComponent(options.receipt_id)}`
        : options.expense_id
          ? `${groupPath(groupId)}/expenses/${encodeURIComponent(options.expense_id)}/receipt`
          : null
      if (!path) return null
      try {
        return await api.get(path, { signal: read.signal })
      } catch (error) {
        if (
          error &&
          typeof error === 'object' &&
          'code' in error &&
          /** @type {{code?: unknown}} */ (error).code === 'not_found'
        ) {
          return null
        }
        throw error
      }
    })
  },
  /**
   * Upload a receipt image (online only in M1).
   *
   * @param {string} groupId
   * @param {File|Blob} file
   * @param {{signal?: AbortSignal, width?: number, height?: number}} [options]
   * @returns {Promise<{url: string, width: number, height: number}>}
   */
  async upload(groupId, file, options = {}) {
    return run(async () => {
      const form = new FormData()
      form.append('file', file)
      form.append('width', String(options.width || 1))
      form.append('height', String(options.height || 1))
      return /** @type {{url: string, width: number, height: number}} */ (
        await api.post(`${groupPath(groupId)}/receipts/upload`, {
          body: form,
          signal: options.signal,
        })
      )
    })
  },
  /**
   * @param {string} groupId
   * @param {{image_url: string}} input
   * @param {ReadOptions} [options]
   * @returns {Promise<any>}
   */
  async extractTotal(groupId, input, options = {}) {
    return run(async () =>
      api.post(`${groupPath(groupId)}/receipts/extract-total`, {
        body: input,
        signal: options.signal,
      }),
    )
  },
  /**
   * @param {string} groupId
   * @param {any} input
   * @param {ReadOptions} [options]
   * @returns {Promise<any>}
   */
  async extractItems(groupId, input, options = {}) {
    return run(async () =>
      api.post(`${groupPath(groupId)}/receipts/extract-items`, {
        body: input,
        signal: options.signal,
      }),
    )
  },
  /**
   * @param {string} groupId
   * @param {string} receiptId
   * @param {any} input
   * @param {ReadOptions} [options]
   * @returns {Promise<any>}
   */
  async addItem(groupId, receiptId, input, options = {}) {
    return run(async () =>
      api.post(`${groupPath(groupId)}/receipts/${encodeURIComponent(receiptId)}/items`, {
        body: input,
        signal: options.signal,
      }),
    )
  },
  /**
   * @param {string} groupId
   * @param {string} receiptId
   * @param {string} itemId
   * @param {any} input
   * @param {ReadOptions} [options]
   * @returns {Promise<any>}
   */
  async updateItem(groupId, receiptId, itemId, input, options = {}) {
    return run(async () =>
      api.patch(
        `${groupPath(groupId)}/receipts/${encodeURIComponent(receiptId)}/items/${encodeURIComponent(itemId)}`,
        { body: input, signal: options.signal },
      ),
    )
  },
  /**
   * @param {string} groupId
   * @param {string} receiptId
   * @param {string} itemId
   * @param {ReadOptions} [options]
   * @returns {Promise<any>}
   */
  async deleteItem(groupId, receiptId, itemId, options = {}) {
    return run(async () =>
      api.delete(
        `${groupPath(groupId)}/receipts/${encodeURIComponent(receiptId)}/items/${encodeURIComponent(itemId)}`,
        { signal: options.signal },
      ),
    )
  },
  /**
   * @param {string} groupId
   * @param {string} receiptId
   * @param {string} itemId
   * @param {any[]} portions
   * @param {ReadOptions} [options]
   * @returns {Promise<any>}
   */
  async setPortions(groupId, receiptId, itemId, portions, options = {}) {
    return run(async () =>
      api.put(
        `${groupPath(groupId)}/receipts/${encodeURIComponent(receiptId)}/items/${encodeURIComponent(itemId)}/portions`,
        { body: { portions }, signal: options.signal },
      ),
    )
  },
  /**
   * @param {string} groupId
   * @param {string} receiptId
   * @param {string} participantId
   * @param {boolean} value
   * @param {ReadOptions} [options]
   * @returns {Promise<any>}
   */
  async setOptOut(groupId, receiptId, participantId, value, options = {}) {
    return run(async () =>
      api.put(
        `${groupPath(groupId)}/receipts/${encodeURIComponent(receiptId)}/opt-outs/${encodeURIComponent(participantId)}`,
        { body: { opted_out: value }, signal: options.signal },
      ),
    )
  },
  /**
   * @param {string} groupId
   * @param {string} receiptId
   * @param {{expense_id: string, participant_id?: string}} input
   * @param {ReadOptions} [options]
   * @returns {Promise<any>}
   */
  async apply(groupId, receiptId, input, options = {}) {
    return run(async () =>
      api.post(`${groupPath(groupId)}/receipts/${encodeURIComponent(receiptId)}/apply`, {
        body: input,
        signal: options.signal,
      }),
    )
  },
  /**
   * @param {string} groupId
   * @param {string} receiptId
   * @param {string} expenseId
   * @param {ReadOptions} [options]
   * @returns {Promise<any>}
   */
  async link(groupId, receiptId, expenseId, options = {}) {
    return run(async () =>
      api.post(`${groupPath(groupId)}/receipts/${encodeURIComponent(receiptId)}/link`, {
        body: { expense_id: expenseId },
        signal: options.signal,
      }),
    )
  },
}

const documents = {
  /**
   * @param {string} groupId
   * @param {string} expenseId
   * @param {File|Blob} file
   * @param {{signal?: AbortSignal, width?: number, height?: number}} [options]
   * @returns {Promise<any>}
   */
  async upload(groupId, expenseId, file, options = {}) {
    return run(async () => {
      const form = new FormData()
      form.append('file', file)
      form.append('width', String(options.width || 1))
      form.append('height', String(options.height || 1))
      return api.post(
        `${groupPath(groupId)}/expenses/${encodeURIComponent(expenseId)}/documents`,
        { body: form, signal: options.signal },
      )
    })
  },
  /**
   * @param {string} groupId
   * @param {string} expenseId
   * @param {string} documentId
   * @param {ReadOptions} [options]
   * @returns {Promise<void>}
   */
  async remove(groupId, expenseId, documentId, options = {}) {
    await run(async () =>
      api.delete(
        `${groupPath(groupId)}/expenses/${encodeURIComponent(expenseId)}/documents/${encodeURIComponent(documentId)}`,
        { signal: options.signal },
      ),
    )
  },
}

const exportsRepository = {
  /**
   * @param {string} groupId
   * @param {any} [options]
   * @param {ReadOptions} [read]
   * @returns {Promise<{filename: string, content: string}>}
   */
  async csv(groupId, options = {}, read = {}) {
    return run(async () => {
      const result = await api.text(
        `${groupPath(groupId)}/expenses/export.csv${query({
          from: options.from,
          to: options.to,
        })}`,
        { signal: read.signal || options.signal },
      )
      return {
        filename: result.filename || `spliit-${groupId}.csv`,
        content: result.content,
      }
    })
  },
  /**
   * @param {string} groupId
   * @param {any} [options]
   * @param {ReadOptions} [read]
   * @returns {Promise<{filename: string, content: string}>}
   */
  async json(groupId, options = {}, read = {}) {
    return run(async () => {
      const result = await api.text(
        `${groupPath(groupId)}/expenses/export.json${query({
          from: options.from,
          to: options.to,
        })}`,
        { signal: read.signal || options.signal },
      )
      return {
        filename: result.filename || `spliit-${groupId}.json`,
        content: result.content,
      }
    })
  },
}

const features = {
  /**
   * @param {ReadOptions} [options]
   * @returns {Promise<any>}
   */
  async get(options = {}) {
    return run(async () => api.get('/features', { signal: options.signal }))
  },
}

const admin = {
  /**
   * @param {ReadOptions} [options]
   * @returns {Promise<any>}
   */
  async metrics(options = {}) {
    return run(async () => api.get('/admin/metrics', { signal: options.signal }))
  },
  users: {
    /**
     * @param {{q?: string, tier?: string, limit?: number, offset?: number}} [input]
     * @param {ReadOptions} [options]
     * @returns {Promise<any>}
     */
    async list(input = {}, options = {}) {
      return run(async () =>
        api.get(
          `/admin/users${query({ q: input.q, tier: input.tier, limit: input.limit, offset: input.offset })}`,
          { signal: options.signal },
        ),
      )
    },
    /**
     * @param {{email: string, tier?: string, name?: string}} input
     * @param {ReadOptions} [options]
     * @returns {Promise<any>}
     */
    async preauthorize(input, options = {}) {
      return run(async () =>
        api.post('/admin/users/preauthorize', { body: input, signal: options.signal }),
      )
    },
    /**
     * @param {string} userId
     * @param {string} tier
     * @param {ReadOptions} [options]
     * @returns {Promise<any>}
     */
    async setTier(userId, tier, options = {}) {
      return run(async () =>
        api.patch(`/admin/users/${encodeURIComponent(userId)}/tier`, {
          body: { tier },
          signal: options.signal,
        }),
      )
    },
    /**
     * @param {string} userId
     * @param {ReadOptions} [options]
     * @returns {Promise<void>}
     */
    async remove(userId, options = {}) {
      await run(async () =>
        api.delete(`/admin/users/${encodeURIComponent(userId)}`, { signal: options.signal }),
      )
    },
  },
  groups: {
    /**
     * @param {{q?: string, limit?: number, offset?: number}} [input]
     * @param {ReadOptions} [options]
     * @returns {Promise<any>}
     */
    async list(input = {}, options = {}) {
      return run(async () =>
        api.get(
          `/admin/groups${query({ q: input.q, limit: input.limit, offset: input.offset })}`,
          { signal: options.signal },
        ),
      )
    },
    /**
     * @param {string} groupId
     * @param {ReadOptions} [options]
     * @returns {Promise<void>}
     */
    async remove(groupId, options = {}) {
      await run(async () =>
        api.delete(`/admin/groups/${encodeURIComponent(groupId)}`, { signal: options.signal }),
      )
    },
  },
}

/**
 * @param {any} input
 * @returns {any}
 */
function normaliseGroupInput(input) {
  if (!input || typeof input !== 'object') return input
  const result = { ...input }
  if (result.currencyCode !== undefined) {
    result.currency_code = result.currencyCode
    delete result.currencyCode
  }
  return result
}

export const onlineRepository = {
  auth,
  groups,
  participants,
  categories,
  expenses,
  balances,
  stats,
  activities,
  receipts,
  documents,
  exports: exportsRepository,
  features,
  admin,
}
