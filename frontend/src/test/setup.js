import '@testing-library/jest-dom/vitest'
import 'fake-indexeddb/auto'

// jsdom does not implement matchMedia; the theme hook relies on it.
if (!window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (/** @type {string} */ query) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  })
}
