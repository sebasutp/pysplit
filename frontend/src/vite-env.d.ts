/// <reference types="vite/client" />

declare module '*.css'
/// <reference types="vite-plugin-pwa/client" />

declare module 'virtual:pwa-register' {
  export function registerSW(options?: Record<string, any>): (reloadPage?: boolean) => Promise<void>
}
