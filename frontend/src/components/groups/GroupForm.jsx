/** Create-group form, validated with zod at the UI boundary. */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { z } from 'zod'

import { repository } from '../../services/repository'
import { saveRecentGroup, setPendingActiveUser } from '../../utils/recent-groups'
import { ErrorState } from '../common/States'
import { Button } from '../ui/Button'
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '../ui/Card'
import { FormField } from '../ui/Form'
import { Input, Textarea } from '../ui/Input'

const participantSchema = z.object({
  id: z.string().optional(),
  name: z.string().min(2, 'min2').max(50, 'max50'),
})

export const groupFormSchema = z
  .object({
    name: z.string().min(2, 'min2').max(50, 'max50'),
    information: z.string().optional(),
    currency: z.string().min(1, 'min1').max(5, 'max5'),
    currencyCode: z.union([z.string().length(3, 'length3'), z.literal('')]),
    participants: z.array(participantSchema).min(1),
  })
  .superRefine(({ participants }, ctx) => {
    participants.forEach((participant, index) => {
      participants.slice(0, index).forEach((other) => {
        if (other.name && other.name === participant.name) {
          ctx.addIssue({
            code: 'custom',
            message: 'duplicateParticipantName',
            path: ['participants', index, 'name'],
          })
        }
      })
    })
  })

/** @typedef {z.infer<typeof groupFormSchema>} GroupFormValues */

const CURRENCY_SYMBOLS = /** @type {Record<string, string>} */ ({
  USD: '$',
  EUR: '€',
  GBP: '£',
  JPY: '¥',
  CNY: '¥',
  INR: '₹',
  BRL: 'R$',
})

/** @param {string} code @returns {string} */
function symbolForCode(code) {
  return CURRENCY_SYMBOLS[code] || code
}

const ERROR_LABELS = /** @type {Record<string, string>} */ ({
  min2: 'Must contain at least 2 characters.',
  max50: 'Must contain at most 50 characters.',
  min1: 'This field is required.',
  max5: 'Must contain at most 5 characters.',
  length3: 'Use a three-letter currency code.',
  duplicateParticipantName: 'Participant names must be unique.',
})

/**
 * @param {{defaultCurrencyCode?: string, initial?: any, onSubmit: (values: GroupFormValues) => Promise<void>, submitLabel?: string}} props
 */
export function GroupForm({
  defaultCurrencyCode = 'USD',
  initial,
  onSubmit,
  submitLabel,
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [values, setValues] = useState(/** @type {GroupFormValues} */ ({
    name: initial?.name || '',
    information: initial?.information || '',
    currency: initial?.currency || symbolForCode(initial?.currency_code || initial?.currencyCode || defaultCurrencyCode),
    currencyCode: initial?.currency_code || initial?.currencyCode || defaultCurrencyCode,
    participants:
      initial?.participants?.length
        ? initial.participants.map((/** @type {any} */ participant) => ({
            id: participant.id,
            name: participant.name,
          }))
        : [
            { name: t('GroupForm.Participants.John', 'John') },
            { name: t('GroupForm.Participants.Jane', 'Jane') },
            { name: t('GroupForm.Participants.Jack', 'Jack') },
          ],
  }))
  const [errors, setErrors] = useState(/** @type {Record<string, string>} */ ({}))
  const [pending, setPending] = useState(false)
  const [submitError, setSubmitError] = useState('')

  /** @param {string} field @param {string} value */
  function update(field, value) {
    setValues((previous) => ({ ...previous, [field]: value }))
  }

  /** @param {number} index @param {string} value */
  function updateParticipant(index, value) {
    setValues((previous) => ({
      ...previous,
      participants: previous.participants.map((participant, current) =>
        current === index ? { ...participant, name: value } : participant,
      ),
    }))
  }

  /** @param {React.FormEvent} event */
  async function handleSubmit(event) {
    event.preventDefault()
    setSubmitError('')
    const parsed = groupFormSchema.safeParse(values)
    if (!parsed.success) {
      /** @type {Record<string, string>} */
      const next = {}
      for (const issue of parsed.error.issues) {
        const key = issue.path.join('.') || 'form'
        next[key] = ERROR_LABELS[/** @type {string} */ (issue.message)] || issue.message
      }
      setErrors(next)
      return
    }
    setErrors({})
    setPending(true)
    try {
      await onSubmit(parsed.data)
    } catch (error) {
      const detail =
        error && typeof error === 'object' && 'detail' in error
          ? String(/** @type {{detail: unknown}} */ (error).detail)
          : 'Could not save the group.'
      setSubmitError(detail)
    } finally {
      setPending(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      {submitError ? (
        <div className="mb-4">
          <ErrorState title={submitError} />
        </div>
      ) : null}
      <Card className="mb-4">
        <CardHeader>
          <CardTitle>{t('GroupForm.title', 'Group information')}</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <FormField
            label={t('GroupForm.NameField.label', 'Group name')}
            htmlFor="group-name"
            description={t('GroupForm.NameField.description', 'Enter a name for your group.')}
            error={errors.name}
          >
            <Input
              id="group-name"
              name="name"
              className="text-base"
              placeholder={t('GroupForm.NameField.placeholder', 'Summer vacations')}
              value={values.name}
              onChange={(event) => update('name', event.target.value)}
            />
          </FormField>

          <FormField
            label={t('GroupForm.CurrencyCodeField.label', 'Main currency')}
            htmlFor="group-currency-code"
            description={t(
              'GroupForm.CurrencyCodeField.createDescription',
              'All amounts and balances will be in this currency.',
            )}
            error={errors.currencyCode}
          >
            <Input
              id="group-currency-code"
              name="currencyCode"
              className="text-base"
              maxLength={3}
              value={values.currencyCode}
              onChange={(event) => update('currencyCode', event.target.value.toUpperCase())}
            />
          </FormField>

          <FormField
            label={t('GroupForm.CurrencyField.label', 'Currency symbol')}
            htmlFor="group-currency"
            description={t('GroupForm.CurrencyField.description', 'We’ll use it to display amounts.')}
            error={errors.currency}
          >
            <Input
              id="group-currency"
              name="currency"
              className="text-base"
              placeholder={t('GroupForm.CurrencyField.placeholder', '$, €, £…')}
              maxLength={5}
              value={values.currency}
              onChange={(event) => update('currency', event.target.value)}
            />
          </FormField>

          <div className="sm:col-span-2">
            <FormField
              label={t('GroupForm.InformationField.label', 'Group information')}
              htmlFor="group-information"
              error={errors.information}
            >
              <Textarea
                id="group-information"
                name="information"
                rows={2}
                className="text-base"
                placeholder={t(
                  'GroupForm.InformationField.placeholder',
                  'What information is relevant to group participants?',
                )}
                value={values.information}
                onChange={(event) => update('information', event.target.value)}
              />
            </FormField>
          </div>
        </CardContent>
      </Card>

      <Card className="mb-4">
        <CardHeader>
          <CardTitle>{t('GroupForm.Participants.title', 'Participants')}</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="flex flex-col gap-2">
            {values.participants.map((participant, index) => (
              <li key={participant.id || index}>
                <div className="flex gap-2">
                  <label className="sr-only" htmlFor={`participant-${index}`}>
                    Participant #{index + 1}
                  </label>
                  <Input
                    id={`participant-${index}`}
                    name={`participants.${index}.name`}
                    className="text-base"
                    placeholder={t('GroupForm.Participants.new', 'New')}
                    value={participant.name}
                    onChange={(event) => updateParticipant(index, event.target.value)}
                  />
                  <Button
                    variant="ghost"
                    size="icon"
                    className="text-destructive"
                    aria-label={`Remove participant ${index + 1}`}
                    disabled={values.participants.length === 1}
                    onClick={() =>
                      setValues((previous) => ({
                        ...previous,
                        participants: previous.participants.filter(
                          (_item, current) => current !== index,
                        ),
                      }))
                    }
                  >
                    🗑
                  </Button>
                </div>
                {errors[`participants.${index}.name`] ? (
                  <p role="alert" className="mt-1 text-xs text-destructive">
                    {errors[`participants.${index}.name`]}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </CardContent>
        <CardFooter>
          <Button
            variant="secondary"
            onClick={() =>
              setValues((previous) => ({
                ...previous,
                participants: [...previous.participants, { name: '' }],
              }))
            }
          >
            {t('GroupForm.Participants.add', 'Add participant')}
          </Button>
        </CardFooter>
      </Card>

      <div className="mt-4 flex gap-2">
        <Button type="submit" disabled={pending}>
          {pending
            ? t('GroupForm.Settings.creating', 'Creating…')
            : submitLabel || t('GroupForm.Settings.create', 'Create')}
        </Button>
        <Button variant="ghost" onClick={() => navigate('/groups')}>
          {t('GroupForm.Settings.cancel', 'Cancel')}
        </Button>
      </div>
    </form>
  )
}

/**
 * @param {{defaultCurrencyCode?: string}} props
 */
export function CreateGroup({ defaultCurrencyCode = 'USD' }) {
  const navigate = useNavigate()
  return (
    <GroupForm
      defaultCurrencyCode={defaultCurrencyCode}
      onSubmit={async (values) => {
        const group = await repository.groups.create({
          name: values.name,
          information: values.information || null,
          currency: values.currency,
          currencyCode: values.currencyCode || null,
          participants: values.participants.map((participant) => ({
            ...(participant.id ? { id: participant.id } : {}),
            name: participant.name,
          })),
        })
        saveRecentGroup({ id: group.id, name: group.name })
        setPendingActiveUser(null)
        navigate(`/groups/${group.id}`)
      }}
    />
  )
}
