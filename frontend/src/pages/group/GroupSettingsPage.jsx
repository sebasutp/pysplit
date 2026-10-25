/** /groups/:groupId/edit */

import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'

import { useGroupContext } from '../../components/groups/GroupLayout'
import { GroupForm } from '../../components/groups/GroupForm'
import { useToast } from '../../hooks/useToast'
import { repository } from '../../services/repository'

export function GroupSettingsPage() {
  // The layout already loads the group and its details once per visit; reuse
  // that data instead of issuing the same four requests again.
  const { group, details, reloadGroup } = useGroupContext()
  const { t } = useTranslation()
  const { toast } = useToast()
  const locked = details?.participants_with_expenses || []

  // Refresh once on mount: a participant may have joined an expense since the
  // layout loaded, which changes the locked participant list. reloadGroup is a
  // stable callback, so this cannot loop.
  useEffect(() => {
    void reloadGroup()
  }, [reloadGroup])

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-xl font-semibold">
        {t('Settings.title', 'Settings')}
      </h2>
      <GroupForm
        initial={{ ...group, participants: group.participants || [] }}
        lockedParticipantIds={locked}
        submitLabel={t('ExpenseForm.save', 'Save')}
        onSubmit={async (values) => {
          const updated = await repository.groups.update(group.id, {
            name: values.name,
            information: values.information || null,
            currency: values.currency,
            currencyCode: values.currencyCode || null,
            participants: values.participants.map((participant) => ({
              ...(participant.id ? { id: participant.id } : {}),
              name: participant.name,
            })),
          })
          toast({
            title: t('Settings.saved', 'Group updated'),
            description: t('Settings.savedDescription', 'Your changes have been saved.'),
          })
          void updated
          // Refresh the shared group/details state after saving.
          await reloadGroup()
        }}
      />
    </section>
  )
}
