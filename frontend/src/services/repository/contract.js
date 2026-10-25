/**
 * Canonical repository contract.
 *
 * Components and hooks import `repository` from this folder and nothing else.
 * The online implementation is a thin pass-through in M1; Stage 9A adds the
 * Dexie implementation with exactly the same surface. See
 * docs/repository-contract.md for the normative description.
 */

export class RepositoryError extends Error {
  /**
   * @param {string} message
   * @param {Object} [options]
   * @param {string} [options.code]
   * @param {number|null} [options.status]
   * @param {string} [options.detail]
   * @param {Record<string, unknown>} [options.fields]
   * @param {boolean} [options.retryable]
   */
  constructor(message, options = {}) {
    super(message)
    this.name = 'RepositoryError'
    this.code = options.code ?? 'server'
    this.status = options.status ?? null
    this.detail = options.detail ?? message
    this.fields = options.fields
    this.retryable = options.retryable ?? false
  }
}

/**
 * Method paths every repository implementation must expose. The contract test
 * uses this list, so adding a method here is the only way to make it part of
 * the frozen interface.
 */
export const REPOSITORY_METHODS = [
  'auth.me',
  'auth.refresh',
  'auth.logout',
  'auth.startOAuth',
  'auth.isAuthenticated',
  'auth.providers',
  'groups.list',
  'groups.get',
  'groups.details',
  'groups.create',
  'groups.update',
  'groups.removeMembership',
  'groups.recordAccess',
  'groups.setStarred',
  'groups.setArchived',
  'groups.sync',
  'participants.list',
  'participants.upsert',
  'participants.remove',
  'categories.list',
  'categories.infer',
  'expenses.list',
  'expenses.get',
  'expenses.create',
  'expenses.update',
  'expenses.remove',
  'balances.list',
  'balances.forUser',
  'stats.overview',
  'stats.categoryExpenses',
  'stats.monthExpenses',
  'activities.list',
  'receipts.get',
  'receipts.extractTotal',
  'receipts.extractItems',
  'receipts.addItem',
  'receipts.updateItem',
  'receipts.deleteItem',
  'receipts.setPortions',
  'receipts.setOptOut',
  'receipts.apply',
  'receipts.link',
  'documents.upload',
  'documents.remove',
  'exports.csv',
  'exports.json',
  'sync.status',
  'sync.now',
  'sync.onStatus',
  'sync.conflicts.list',
  'sync.conflicts.resolve',
]

/**
 * @param {unknown} error
 * @returns {RepositoryError}
 */
export function toRepositoryError(error) {
  if (error instanceof RepositoryError) return error
  if (error && typeof error === 'object') {
    const candidate = /** @type {{name?: unknown, message?: unknown, code?: unknown, status?: unknown, detail?: unknown, fields?: unknown, retryable?: unknown}} */ (
      error
    )
    if (candidate.name === 'ApiError' || typeof candidate.code === 'string') {
      return new RepositoryError(
        typeof candidate.message === 'string' ? candidate.message : 'Request failed',
        {
          code: typeof candidate.code === 'string' ? candidate.code : 'server',
          status: typeof candidate.status === 'number' ? candidate.status : null,
          detail:
            typeof candidate.detail === 'string'
              ? candidate.detail
              : typeof candidate.message === 'string'
                ? candidate.message
                : 'Request failed',
          fields:
            candidate.fields && typeof candidate.fields === 'object'
              ? /** @type {Record<string, unknown>} */ (candidate.fields)
              : undefined,
          retryable: Boolean(candidate.retryable),
        },
      )
    }
  }
  if (error && typeof error === 'object' && 'name' in error && error.name === 'AbortError') {
    return new RepositoryError('Request aborted', { code: 'aborted' })
  }
  return new RepositoryError(error instanceof Error ? error.message : 'Request failed', {
    code: 'network',
    retryable: true,
  })
}

/**
 * Execute a repository body and guarantee only RepositoryError escapes.
 *
 * @template T
 * @param {() => Promise<T>} action
 * @returns {Promise<T>}
 */
export async function run(action) {
  try {
    return await action()
  } catch (error) {
    throw toRepositoryError(error)
  }
}
