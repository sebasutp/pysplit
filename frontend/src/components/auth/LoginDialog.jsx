/**
 * Sign-in dialog for Google and GitHub OAuth.
 */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useAuth } from '../../hooks/useAuth'
import { Button } from '../ui/Button'
import { Alert, AlertDescription } from '../ui/Feedback'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../ui/Dialog'

/**
 * @param {{trigger?: React.ReactNode, open?: boolean, onOpenChange?: (open: boolean) => void}} props
 */
export function LoginDialog({ trigger, open: controlledOpen, onOpenChange }) {
  const { t } = useTranslation()
  const { providers, login } = useAuth()
  const [internalOpen, setInternalOpen] = useState(false)
  const isControlled = controlledOpen !== undefined
  const open = isControlled ? controlledOpen : internalOpen
  const setOpen = isControlled ? onOpenChange || (() => {}) : setInternalOpen
  const hasGoogle = Boolean(providers.google)
  const hasGithub = Boolean(providers.github)

  /** @param {'google'|'github'} provider */
  const handleLogin = (provider) => {
    login(provider, window.location.pathname)
  }

  return (
    <>
      {trigger ? (
        <span onClick={() => setOpen(true)} className="inline-flex">
          {trigger}
        </span>
      ) : null}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t('Login.title', 'Sign in to Spliit')}</DialogTitle>
            <DialogDescription>
              {t(
                'Login.description',
                'Sign in with an external account to enable cross-device group synchronization.',
              )}
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-3 py-4">
            {hasGoogle ? (
              <Button variant="outline" className="w-full py-5" onClick={() => handleLogin('google')}>
                {t('Login.google', 'Continue with Google')}
              </Button>
            ) : null}
            {hasGithub ? (
              <Button variant="outline" className="w-full py-5" onClick={() => handleLogin('github')}>
                {t('Login.github', 'Continue with GitHub')}
              </Button>
            ) : null}
            {!hasGoogle && !hasGithub ? (
              <Alert>
                <AlertDescription>
                  {t(
                    'Login.noProviders',
                    'No OAuth providers are configured. Set AUTH_GOOGLE_ID / AUTH_GOOGLE_SECRET to enable sign-in.',
                  )}
                </AlertDescription>
              </Alert>
            ) : null}
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
