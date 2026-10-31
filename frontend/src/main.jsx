import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import App from './App'
import { startSync } from './services/repository'
import { startPwa } from './services/pwa'
import { stabilizeResourceTiming } from './utils/resource-timing'
import './styles/index.css'

// Install before the first render: React's Suspense image estimator reads
// Resource Timing entries during commit.
stabilizeResourceTiming()

const container = document.getElementById('root')
if (!container) {
  throw new Error('Root container #root is missing from index.html')
}

startSync()
startPwa()

createRoot(container).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
