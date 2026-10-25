/**
 * Zod validation for the expense form, ported from the reference
 * `src/lib/schemas.ts` expense schema. Split-amount and percentage sum checks
 * stay in the form because they depend on the selected participants.
 */

import { z } from 'zod'

import { parseAmount } from '../utils/currency'

export const expenseFormSchema = z.object({
  title: z.string().trim().min(2, 'titleMin'),
  amount: z.string().refine((value) => parseAmount(value) !== 0, 'amountNotZero'),
  expenseDate: z.string().min(1, 'dateRequired'),
  categoryId: z.union([z.string(), z.number()]),
  paidById: z.string().min(1, 'paidByRequired'),
  splitMode: z.enum(['EVENLY', 'BY_SHARES', 'BY_PERCENTAGE', 'BY_AMOUNT']),
  recurrence: z.enum(['NONE', 'DAILY', 'WEEKLY', 'MONTHLY']),
  paidFor: z
    .array(
      z.object({
        participant_id: z.string().min(1),
        checked: z.boolean(),
        share: z.string(),
      }),
    )
    .refine((rows) => rows.some((row) => row.checked), 'participantsRequired'),
  originalCurrency: z.string().optional(),
  originalAmount: z.string().optional(),
  conversionRate: z.string().optional(),
  notes: z.string().optional(),
})

/** @typedef {z.infer<typeof expenseFormSchema>} ExpenseFormValues */

export const EXPENSE_ERROR_LABELS = /** @type {Record<string, string>} */ ({
  titleMin: 'Title must contain at least 2 characters.',
  amountNotZero: 'Amount must not be zero.',
  dateRequired: 'Choose an expense date.',
  paidByRequired: 'Select who paid.',
  participantsRequired: 'Select at least one participant.',
})
