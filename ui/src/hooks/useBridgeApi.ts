import { useCallback } from 'react'
import type {
  ActivityItem,
  ActivitySnapshotResponse,
  AgentOrchestratorModel,
  AgentOrchestratorModelsResult,
  BootstrapResponse,
  LiveDiagnosticsResult,
  AgentOrchestratorResult,
  McpConnectionStatus,
  McpToolCallRecord,
  RunStatus,
  SavedSettings,
  SessionStateSnapshot,
  WorkspaceDraft,
} from '../types'
import {
  mapUiSettingsToApi,
  normalizeActivitySnapshotResponse,
  normalizeBootstrapResponse,
  normalizeConsoleLogPayload,
  normalizeLiveDiagnostics,
  normalizeMcpStatus,
  normalizeMcpToolCalls,
  normalizeRunStatus,
  normalizeSessionStateSnapshot,
} from '../utils/normalizers'
import { defaultSettings } from '../data/sampleSession'

async function readJson(response: Response) {
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }
  return response.json()
}

export function useBridgeApi() {
  const bootstrap = useCallback(async (): Promise<BootstrapResponse> => {
    const payload = await readJson(await fetch('/api/bootstrap'))
    return normalizeBootstrapResponse(payload, defaultSettings)
  }, [])

  const getSessionState = useCallback(async (sessionId: string): Promise<SessionStateSnapshot> => {
    const payload = await readJson(
      await fetch(`/api/session/state?session_id=${encodeURIComponent(sessionId)}`),
    )
    return normalizeSessionStateSnapshot(payload)
  }, [])

  const getActivitySnapshot = useCallback(async (sessionId: string): Promise<ActivitySnapshotResponse> => {
    const payload = await readJson(
      await fetch(`/api/activity/snapshot?session_id=${encodeURIComponent(sessionId)}`),
    )
    return normalizeActivitySnapshotResponse(payload)
  }, [])

  const createSession = useCallback(async (): Promise<{ session_id: string }> => {
    return readJson(await fetch('/api/session/new', { method: 'POST' }))
  }, [])

  const deleteSession = useCallback(async (sessionId: string) => {
    return readJson(
      await fetch('/api/session/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
      }),
    )
  }, [])

  const saveWorkspace = useCallback(async (sessionId: string, workspace: WorkspaceDraft, title?: string) => {
    return readJson(
      await fetch('/api/session/workspace', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          task_input: workspace.taskInput,
          reference_text: workspace.referenceText,
          reference_images: workspace.referenceImages,
          title,
        }),
      }),
    )
  }, [])

  const appendActivity = useCallback(async (sessionId: string, activity: ActivityItem[]) => {
    return readJson(
      await fetch('/api/activity/append', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, activity }),
      }),
    )
  }, [])

  const setCurrentSession = useCallback(async (sessionId: string) => {
    return readJson(
      await fetch('/api/session/current', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
      }),
    )
  }, [])

  const fetchMcpStatus = useCallback(async (): Promise<McpConnectionStatus> => {
    const payload = await readJson(await fetch('/api/mcp/status'))
    return normalizeMcpStatus(payload)
  }, [])

  const fetchRunStatus = useCallback(async (sessionId: string): Promise<RunStatus> => {
    const payload = await readJson(await fetch(`/api/run/status?session_id=${encodeURIComponent(sessionId)}`))
    return normalizeRunStatus(payload)
  }, [])

  const fetchConsoleLog = useCallback(async (sessionId: string): Promise<string> => {
    const payload = await readJson(await fetch(`/api/run/console?session_id=${encodeURIComponent(sessionId)}`))
    return normalizeConsoleLogPayload(payload)
  }, [])

  const fetchMcpToolCalls = useCallback(async (sessionId: string): Promise<McpToolCallRecord[]> => {
    const payload = await readJson(
      await fetch(`/api/mcp/tool-calls?session_id=${encodeURIComponent(sessionId)}`),
    )
    return normalizeMcpToolCalls(payload.tool_calls)
  }, [])

  const verifyAgentOrchestrator = useCallback(async (settings: SavedSettings): Promise<AgentOrchestratorResult> => {
    return readJson(
      await fetch('/api/agent-orchestrator/live', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(mapUiSettingsToApi(settings)),
      }),
    )
  }, [])

  const listAgentOrchestratorModels = useCallback(async (settings: SavedSettings): Promise<AgentOrchestratorModelsResult> => {
    const payload = await readJson(
      await fetch('/api/agent-orchestrator/models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(mapUiSettingsToApi(settings)),
      }),
    )
    const rawModels = Array.isArray(payload.models) ? payload.models : []
    const models: AgentOrchestratorModel[] = (rawModels as unknown[])
      .filter((item: unknown): item is Record<string, unknown> => typeof item === 'object' && item !== null)
      .map((item: Record<string, unknown>) => ({
        id: String(item.id ?? ''),
        provider: String(item.provider ?? ''),
        model: String(item.model ?? ''),
      }))
      .filter((item: AgentOrchestratorModel) => item.id.trim())
    return {
      ok: Boolean(payload.ok ?? false),
      models,
      message: String(payload.message ?? ''),
    }
  }, [])

  const runLiveDiagnostics = useCallback(
    async (currentSessionId: string, settings: SavedSettings): Promise<LiveDiagnosticsResult> => {
      const payload = await readJson(
        await fetch('/api/diagnostics/live', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: currentSessionId, ...mapUiSettingsToApi(settings) }),
        }),
      )
      return normalizeLiveDiagnostics(payload)
    },
    [],
  )

  const syncBlenderMcp = useCallback(async (): Promise<McpConnectionStatus> => {
    const payload = await readJson(
      await fetch('/api/mcp/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    return normalizeMcpStatus(payload)
  }, [])

  const saveRemoteSettings = useCallback(async (settings: SavedSettings) => {
    return readJson(
      await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(mapUiSettingsToApi(settings)),
      }),
    )
  }, [])

  const startRun = useCallback(
    async (
      sessionId: string,
      settings: SavedSettings,
      workspace: WorkspaceDraft,
    ): Promise<{ started: boolean; session_id: string; run_status: RunStatus; error_message?: string }> => {
      const payload = await readJson(
        await fetch('/api/run/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            task: String(workspace.taskInput ?? ''),
            session_id: sessionId,
            ...mapUiSettingsToApi(settings),
            reference_texts: String(workspace.referenceText ?? '')
              .split('\n')
              .map((item) => item.trim())
              .filter(Boolean),
            reference_images: Array.isArray(workspace.referenceImages) ? workspace.referenceImages : [],
            max_part_refinement_rounds: settings.maxPartRefinementRounds,
            max_assembly_rounds: settings.maxAssemblyRounds,
            use_yolo_perception: settings.useYoloValidation,
            yolo_model_path: String(settings.yoloModelPath ?? ''),
            yolo_viewpoints: String(settings.yoloViewpoints ?? '')
              .split(',')
              .map((item) => item.trim())
              .filter(Boolean),
          }),
        }),
      )
      return {
        ...payload,
        run_status: normalizeRunStatus(payload.run_status),
      }
    },
    [],
  )

  const stopRun = useCallback(async (sessionId: string) => {
    const payload = await readJson(
      await fetch('/api/run/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
      }),
    )
    return {
      ...payload,
      run_status: normalizeRunStatus(payload.run_status),
    }
  }, [])

  const retryRun = useCallback(async (sessionId: string, retryCount: number) => {
    const payload = await readJson(
      await fetch('/api/run/retry', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, retry_count: retryCount }),
      }),
    )
    return {
      ...payload,
      run_status: normalizeRunStatus(payload.run_status),
    }
  }, [])

  const clearRetryPrompt = useCallback(async (sessionId: string) => {
    return readJson(
      await fetch('/api/run/retry/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
      }),
    )
  }, [])

  return {
    appendActivity,
    bootstrap,
    clearRetryPrompt,
    createSession,
    deleteSession,
    fetchConsoleLog,
    fetchMcpStatus,
    fetchMcpToolCalls,
    fetchRunStatus,
    getActivitySnapshot,
    getSessionState,
    listAgentOrchestratorModels,
    retryRun,
    runLiveDiagnostics,
    saveRemoteSettings,
    saveWorkspace,
    setCurrentSession,
    startRun,
    stopRun,
    syncBlenderMcp,
    verifyAgentOrchestrator,
  }
}
