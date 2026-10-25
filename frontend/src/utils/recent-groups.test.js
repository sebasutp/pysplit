import { beforeEach, describe, expect, it } from 'vitest'

import {
  clearPendingActiveUser,
  getPendingActiveUser,
  hasPendingActiveUser,
  setPendingActiveUser,
} from './recent-groups'

beforeEach(() => {
  localStorage.clear()
})

describe('pending active user storage', () => {
  it('removes the key when set to null', () => {
    setPendingActiveUser('Alice')
    expect(getPendingActiveUser()).toBe('Alice')

    setPendingActiveUser(null)
    expect(localStorage.getItem('newGroup-activeUser')).toBeNull()
    expect(hasPendingActiveUser()).toBe(false)

    setPendingActiveUser('Bob')
    clearPendingActiveUser()
    expect(localStorage.getItem('newGroup-activeUser')).toBeNull()
  })

  it('treats the legacy "None" value as absent', () => {
    localStorage.setItem('newGroup-activeUser', 'None')
    expect(getPendingActiveUser()).toBeNull()
  })
})
