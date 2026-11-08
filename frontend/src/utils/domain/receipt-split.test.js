import { describe, expect, it } from 'vitest'

import { getItemDestinations } from './receipt-split'

const participants = ['a', 'b']

describe('getItemDestinations', () => {
  it('merges duplicate participant portions and sums their amounts', () => {
    const destinations = getItemDestinations(
      {
        amount: 1350,
        quantity_milli: 3000,
        portions: [
          { target: 'PARTICIPANT', participant_id: 'a', quantity_milli: 1000 },
          { target: 'PARTICIPANT', participant_id: 'a', quantity_milli: 1000 },
          { target: 'PARTICIPANT', participant_id: 'b', quantity_milli: 1000 },
        ],
      },
      participants,
    )

    expect(destinations).toEqual([
      { target: 'PARTICIPANT', participantId: 'a', quantityMilli: 2000, amount: 900 },
      { target: 'PARTICIPANT', participantId: 'b', quantityMilli: 1000, amount: 450 },
    ])
  })

  it('clamps over-assigned portions to the item quantity', () => {
    const destinations = getItemDestinations(
      {
        amount: 1000,
        quantity_milli: 1000,
        portions: [
          { target: 'PARTICIPANT', participant_id: 'a', quantity_milli: 2000 },
          { target: 'PARTICIPANT', participant_id: 'b', quantity_milli: 1000 },
        ],
      },
      participants,
    )

    expect(destinations).toEqual([
      { target: 'PARTICIPANT', participantId: 'a', quantityMilli: 1000, amount: 1000 },
    ])
  })

  it('turns an unknown participant portion into unassigned quantity', () => {
    const destinations = getItemDestinations(
      {
        amount: 1000,
        quantity_milli: 1000,
        portions: [
          { target: 'PARTICIPANT', participant_id: 'stranger', quantity_milli: 1000 },
        ],
      },
      participants,
    )

    expect(destinations).toEqual([
      { target: 'UNASSIGNED', participantId: null, quantityMilli: 1000, amount: 1000 },
    ])
  })

  it('falls back to a fully shared destination for is_shared items', () => {
    const destinations = getItemDestinations(
      { amount: 1000, quantity_milli: 2000, is_shared: true },
      participants,
    )

    expect(destinations).toEqual([
      { target: 'SHARED', participantId: null, quantityMilli: 2000, amount: 1000 },
    ])
  })

  it('treats an is_shared item with quantity 0 as one unassigned unit', () => {
    const destinations = getItemDestinations(
      { amount: 1000, quantity_milli: 0, is_shared: true },
      participants,
    )

    expect(destinations).toEqual([
      { target: 'UNASSIGNED', participantId: null, quantityMilli: 1, amount: 1000 },
    ])
  })

  it('accepts camelCase portion fields', () => {
    const destinations = getItemDestinations(
      {
        amount: 1000,
        quantityMilli: 2000,
        portions: [
          { target: 'PARTICIPANT', participantId: 'a', quantityMilli: 1000 },
          { target: 'SHARED', quantityMilli: 1000 },
        ],
      },
      participants,
    )

    expect(destinations).toEqual([
      { target: 'PARTICIPANT', participantId: 'a', quantityMilli: 1000, amount: 500 },
      { target: 'SHARED', participantId: null, quantityMilli: 1000, amount: 500 },
    ])
  })

  it('splits half units evenly', () => {
    const destinations = getItemDestinations(
      {
        amount: 1350,
        quantity_milli: 1000,
        portions: [
          { target: 'PARTICIPANT', participant_id: 'a', quantity_milli: 500 },
          { target: 'PARTICIPANT', participant_id: 'b', quantity_milli: 500 },
        ],
      },
      participants,
    )

    expect(destinations).toEqual([
      { target: 'PARTICIPANT', participantId: 'a', quantityMilli: 500, amount: 675 },
      { target: 'PARTICIPANT', participantId: 'b', quantityMilli: 500, amount: 675 },
    ])
  })
})
