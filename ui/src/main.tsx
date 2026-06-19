import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ErrorBoundary } from './components/ErrorBoundary'
import './index.css'
import App from './App.tsx'
import { installMcpBrowserMocks } from './dev/mcpBrowserMocks'

if (import.meta.env.VITE_ENABLE_MCP_BROWSER_MOCKS === '1') {
  installMcpBrowserMocks()
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
)
