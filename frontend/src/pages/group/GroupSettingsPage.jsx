/** /groups/:groupId/edit */

import { useTranslation } from 'react-i18next'

import { useGroupContext } from '../../components/groups/GroupLayout'
import { GroupForm } from '../../components/groups/GroupForm'
import { useGroup } from '../../hooks/useGroup'
import { useToast } from '../../hooks/useToast'
import { repository } from '../../services/repository'

export function GroupSettingsPage() {
  const { group: contextGroup, reloadGroup } = useGroupContext()
  // Refresh details on mount: a participant may have joined an expense since
  // the layout first loaded the group.
  const { group: freshGroup, details, reload: reloadDetails } = useGroup(contextGroup.id)
  const group = freshGroup || contextGroup
  const { t } = useTranslation()
  const { toast } = useToast()
  const locked = details?.participants_with_expenses || []

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
          await Promise.all([reloadGroup(), reloadDetails()])
        }}
      />
    </section>
  )
}
