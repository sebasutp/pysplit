/** Add a group by pasted URL. */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { repository } from '../../services/repository'
import { saveRecentGroup } from '../../utils/recent-groups'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'

/**
 * @param {{reload: () => void | Promise<void>}} props
 */
export function AddGroupByUrlButton({ reload }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [url, setUrl] = useState('')
  const [error, setError] = useState(false)
  const [pending, setPending] = useState(false)

  /** @param {string} value @returns {string | null} */
  function groupIdFromUrl(value) {
    try {
      const parsed = new URL(value, window.location.origin)
      if (parsed.origin !== window.location.origin) return null
      return parsed.pathname.match(/^\/groups\/([^/]+)/)?.[1] || null
    } catch {
      return null
    }
  }

  /** @param {React.FormEvent} event */
  async function onSubmit(event) {
    event.preventDefault()
    const groupId = groupIdFromUrl(url)
    if (!groupId) {
      setError(true)
      return
    }
    setPending(true)
    try {
      const group = await repository.groups.get(groupId)
      if (!group) {
        setError(true)
        return
      }
      saveRecentGroup({ id: group.id, name: group.name })
      await reload()
      setUrl('')
      setError(false)
      setOpen(false)
    } catch {
      setError(true)
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="relative">
      <Button variant="secondary" onClick={() => setOpen((value) => !value)}>
        {t('Groups.AddByURL.button', 'Add by URL')}
      </Button>
      {open ? (
        <div className="absolute right-0 top-11 z-40 w-[min(22rem,calc(100vw-2rem))] rounded-md border border-border bg-popover p-4 text-sm shadow-lg">
          <h3 className="font-bold">{t('Groups.AddByURL.title', 'Add a group by URL')}</h3>
          <p className="mt-1 text-muted-foreground">
            {t(
              'Groups.AddByURL.description',
              'If a group was shared with you, you can paste its URL here to add it to your list.',
            )}
          </p>
          <form className="mt-3 flex gap-2" onSubmit={onSubmit}>
            <Input
              type="url"
              required
              placeholder="https://spliit.app/..."
              value={url}
              disabled={pending}
              aria-label={t('Groups.AddByURL.urlMode', 'Enter URL')}
              onChange={(event) => {
                setUrl(event.target.value)
                setError(false)
              }}
            />
            <Button type="submit" size="icon" disabled={pending} aria-label="Add group">
              +
            </Button>
          </form>
          {error ? (
            <p role="alert" className="mt-2 text-destructive">
              {t(
                'Groups.AddByURL.error',
                'Oops, we are not able to find the group from the URL you provided…',
              )}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
