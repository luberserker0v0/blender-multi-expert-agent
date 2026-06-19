import { useEffect, useRef } from 'react'

interface UseAutoVerifyAgentOrchestratorOnSessionEntryOptions {
  currentSessionId: string
  agentOrchestratorUrl: string
  onVerify: () => Promise<void>
}

export function useAutoVerifyAgentOrchestratorOnSessionEntry({
  currentSessionId,
  agentOrchestratorUrl,
  onVerify,
}: UseAutoVerifyAgentOrchestratorOnSessionEntryOptions) {
  const lastVerifiedKeyRef = useRef('')

  useEffect(() => {
    const normalizedUrl = String(agentOrchestratorUrl ?? '').trim()
    if (!currentSessionId || !normalizedUrl) return
    const verificationKey = `${currentSessionId}::${normalizedUrl}`
    if (lastVerifiedKeyRef.current === verificationKey) return
    lastVerifiedKeyRef.current = verificationKey
    void onVerify()
  }, [currentSessionId, agentOrchestratorUrl, onVerify])
}
