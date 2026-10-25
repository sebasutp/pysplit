/**
 * Single repository entry point.
 *
 * M1 selects the online implementation. Stage 9A will swap in the local
 * implementation here (and only here) without changing components or hooks.
 */

import { onlineRepository } from './online'

export { RepositoryError } from './contract'
export const repository = onlineRepository
