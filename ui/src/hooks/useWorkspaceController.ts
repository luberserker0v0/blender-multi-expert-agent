import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  buildInspectorBlocks,
  defaultInspectorSelection,
  getInspectorLatestCapturePath,
  getInspectorSelectedTask,
  getInspectorSelectedTitle,
  getInspectorSelectionKind,
} from '../components/inspector'
import {
  DEFAULT_RETRY_PROMPT,
  DEFAULT_RUN_STATUS,
  DEFAULT_WORKSPACE_DRAFT,
} from '../constants'
import {
  activityItemsFromMeetingEvent,
  createActivityItem,
  createInitialActivityMarkers,
  deriveActivityUpdatesFromProgress,
} from '../domain/activity'
import { defaultSettings } from '../data/sampleSession'
import { useAutoVerifyAgentOrchestratorOnSessionEntry } from './useAutoVerifyAgentOrchestratorOnSessionEntry'
import { useBridgeApi } from './useBridgeApi'
import useActivitySocket from './useActivitySocket'
import useInspector from './useInspector'
import type {
  ActivityEventEnvelope,
  ActivityItem,
  AgentOrchestratorModel,
  MeetingEvent,
  SessionSummary,
  WorkspaceDraft,
} from '../types'
import { deriveSessionTitle } from '../utils/formatters'
import { createEmptyProgress, mergeSessions, resolveCurrentSessionId } from '../utils/normalizers'
import { useWorkspaceStore } from '../store'

function dedupeRenderedActivity(items: ActivityItem[]) {
  const seen = new Set<string>()
  return items.filter((item) => {
    if (!item.id) {
      return true
    }
    if (seen.has(item.id)) {
      return false
    }
    seen.add(item.id)
    return true
  })
}

function reorderSessions(current: SessionSummary[], sessionId: string, title: string) {
  const existing = current.find((session) => session.id === sessionId)
  const nextSession: SessionSummary = {
    id: sessionId,
    title,
    updatedAt: 'just now',
    unread: existing?.unread,
  }
  return [nextSession, ...current.filter((session) => session.id !== sessionId)]
}

export function useWorkspaceController() {
  const api = useBridgeApi()
  const store = useWorkspaceStore()
  const {
    inspectorSelection,
    expandedActivityIds,
    setExpandedActivityIds,
    toggleExpandedActivityId,
  } = useInspector()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [runtimeOpen, setRuntimeOpen] = useState(false)
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [composerExpanded, setComposerExpanded] = useState(true)
  const [pendingDeleteSessionId, setPendingDeleteSessionId] = useState('')
  const [batchDeleteMode, setBatchDeleteMode] = useState(false)
  const [batchDeleteSelectedIds, setBatchDeleteSelectedIds] = useState<string[]>([])
  const [batchDeleteConfirmOpen, setBatchDeleteConfirmOpen] = useState(false)
  const [agentOrchestratorModels, setAgentOrchestratorModels] = useState<AgentOrchestratorModel[]>([])
  const [agentOrchestratorModelsLoading, setAgentOrchestratorModelsLoading] = useState(false)
  const [agentOrchestratorModelsError, setAgentOrchestratorModelsError] = useState('')
  const [initializationState, setInitializationState] = useState<'idle' | 'running' | 'ready' | 'failed'>('idle')
  const localSettingsLoadedRef = useRef(false)
  const sessionActivationRequestRef = useRef(0)

  const currentSessionId = store.currentSessionId
  const currentSession = store.sessions.find((session) => session.id === currentSessionId) ?? null
  const currentWorkspace = store.workspaceDraftsBySessionId[currentSessionId] ?? DEFAULT_WORKSPACE_DRAFT
  const currentActivity = dedupeRenderedActivity(store.activityBySessionId[currentSessionId] ?? [])
  const currentProgress = store.progressBySessionId[currentSessionId] ?? createEmptyProgress()
  const currentRunStatus = store.runStatusBySessionId[currentSessionId] ?? {
    ...DEFAULT_RUN_STATUS,
    session_id: currentSessionId,
  }
  const currentRetryPrompt = store.retryPromptBySessionId[currentSessionId] ?? {
    ...DEFAULT_RETRY_PROMPT,
    session_id: currentSessionId,
  }
  const currentConsoleLog = store.consoleLogBySessionId[currentSessionId] ?? ''
  const currentMcpToolCalls = store.mcpToolCallsBySessionId[currentSessionId] ?? []
  const currentActivityMeta = store.activitySyncMetaBySessionId[currentSessionId]

  const hasSessions = store.sessions.length > 0
  const defaultSelection = defaultInspectorSelection(currentProgress)
  const effectiveInspectorSelection = inspectorSelection ?? defaultSelection
  const selectedTask = getInspectorSelectedTask(effectiveInspectorSelection)
  const selectedInspectorTitle = getInspectorSelectedTitle(effectiveInspectorSelection)
  const latestInspectorCapturePath = getInspectorLatestCapturePath(effectiveInspectorSelection)
  const inspectorSelectionKind = getInspectorSelectionKind(effectiveInspectorSelection)
  const canOperateOnSession = Boolean(currentSessionId && currentSession)
  const agentOrchestratorReady = Boolean(store.agentOrchestratorStatus?.ok)
  const mcpReady = store.mcpStatus.state === 'connected'
  const canStartRun = Boolean(canOperateOnSession && !store.liveDiagnosticsRunning && agentOrchestratorReady && mcpReady)
  const canStopRun = Boolean(canOperateOnSession && currentRunStatus.process_status !== 'not_started')
  const startBlockedReason = !canOperateOnSession
    ? 'Create or open a session before starting a run.'
    : store.liveDiagnosticsRunning
      ? 'Wait for the current Agent Orchestrator verification to finish.'
      : !agentOrchestratorReady
          ? 'Verify Agent Orchestrator before starting.'
        : !mcpReady
          ? 'Blender MCP must be connected before starting.'
          : ''
  const inspectorBlocks = buildInspectorBlocks(effectiveInspectorSelection)

  const persistWorkspace = useCallback(
    async (sessionId: string, workspace: WorkspaceDraft, title?: string) => {
      if (!sessionId) return
      try {
        await api.saveWorkspace(sessionId, workspace, title)
      } catch {
        // Keep local cache when bridge is unavailable.
      }
    },
    [api],
  )

  const persistActivity = useCallback(
    async (sessionId: string, activity: ActivityItem[]) => {
      if (!sessionId || activity.length === 0) return
      try {
        await api.appendActivity(sessionId, activity)
      } catch {
        // Keep optimistic local activity cache.
      }
    },
    [api],
  )

  const applyDerivedActivity = useCallback((sessionId: string) => {
    const progress = useWorkspaceStore.getState().progressBySessionId[sessionId] ?? createEmptyProgress()
    const runStatus = useWorkspaceStore.getState().runStatusBySessionId[sessionId] ?? {
      ...DEFAULT_RUN_STATUS,
      session_id: sessionId,
    }
    const retryPrompt = useWorkspaceStore.getState().retryPromptBySessionId[sessionId] ?? {
      ...DEFAULT_RETRY_PROMPT,
      session_id: sessionId,
    }
    const syncMeta =
      useWorkspaceStore.getState().activitySyncMetaBySessionId[sessionId] ?? {
        lastServerCursor: '',
        lastEventId: '',
        syncState: 'idle' as const,
        markers: createInitialActivityMarkers(),
      }
    const derived = deriveActivityUpdatesFromProgress(progress, runStatus, retryPrompt, syncMeta.markers)
    if (derived.items.length > 0) {
      useWorkspaceStore.getState().appendActivity(sessionId, derived.items)
    }
    useWorkspaceStore.getState().setActivitySyncMeta(sessionId, { markers: derived.markers })
  }, [])

  const applySessionSnapshot = useCallback(
    (sessionId: string, snapshot: Awaited<ReturnType<typeof api.getSessionState>>) => {
      store.hydrateSessionSnapshot(snapshot)
      store.setActivitySyncMeta(sessionId, {
        lastServerCursor: snapshot.server_cursor,
        syncState: 'live',
        markers: createInitialActivityMarkers(),
      })
      applyDerivedActivity(sessionId)
    },
    [applyDerivedActivity, store],
  )

  const syncCurrentSessionState = useCallback(
    async (
      sessionId: string,
      options?: {
        requestId?: number
        syncState?: 'resyncing' | 'stale'
      },
    ) => {
      if (!sessionId) return
      if (options?.syncState) {
        store.setActivitySyncMeta(sessionId, { syncState: options.syncState })
      }
      const snapshot = await api.getSessionState(sessionId)
      if (
        typeof options?.requestId === 'number' &&
        sessionActivationRequestRef.current !== options.requestId
      ) {
        return
      }
      applySessionSnapshot(sessionId, snapshot)
    },
    [api, applySessionSnapshot, store],
  )

  const activateSession = useCallback(
    async (
      sessionId: string,
      options?: {
        clearExpanded?: boolean
        syncRemote?: boolean
      },
    ) => {
      if (!sessionId) return
      const requestId = sessionActivationRequestRef.current + 1
      sessionActivationRequestRef.current = requestId
      if (options?.clearExpanded ?? true) {
        setExpandedActivityIds([])
      }
      store.setCurrentSessionId(sessionId)
      await syncCurrentSessionState(sessionId, {
        requestId,
        syncState: 'resyncing',
      })
      if (sessionActivationRequestRef.current !== requestId) {
        return
      }
      if (options?.syncRemote === false) return
      try {
        await api.setCurrentSession(sessionId)
      } catch {
        // Keep local session selection when bridge is unavailable.
      }
    },
    [api, setExpandedActivityIds, store, syncCurrentSessionState],
  )

  const initializeWorkspaceApp = useCallback(async () => {
    if (initializationState !== 'idle') return
    setInitializationState('running')
    localSettingsLoadedRef.current = Boolean(window.localStorage.getItem('ai3d-react-ui-store'))

    try {
      const payload = await api.bootstrap()
      const localState = useWorkspaceStore.getState()
      const mergedSessions = mergeSessions(localState.sessions, payload.sessions)
      const resolvedSessionId = resolveCurrentSessionId(
        localState.currentSessionId,
        mergedSessions,
        payload.current_session_id,
      )
      store.setSessions(mergedSessions)
      if (!localSettingsLoadedRef.current) {
        store.setSettings(payload.settings ?? defaultSettings)
      }
      if (payload.mcp_status) {
        store.setMcpStatus(payload.mcp_status)
      }
      if (resolvedSessionId) {
        await activateSession(resolvedSessionId, {
          clearExpanded: false,
          syncRemote: false,
        })
      } else {
        sessionActivationRequestRef.current += 1
        store.setCurrentSessionId('')
      }
      setInitializationState('ready')
    } catch {
      if (!localSettingsLoadedRef.current) {
        store.setSettings(defaultSettings)
      }
      setInitializationState('failed')
    }
  }, [activateSession, api, initializationState, store])

  useEffect(() => {
    const initializeTimer = window.setTimeout(() => {
      void initializeWorkspaceApp()
    }, 0)
    return () => window.clearTimeout(initializeTimer)
  }, [initializeWorkspaceApp])

  const handleSocketEnvelope = useCallback(
    (envelope: ActivityEventEnvelope) => {
      const sessionId = envelope.session_id
      if (!sessionId) return
      store.setActivitySyncMeta(sessionId, {
        lastEventId: envelope.event_id,
        lastServerCursor: envelope.server_cursor,
      })

      if (envelope.type === 'meeting_event' && envelope.data) {
        const items = activityItemsFromMeetingEvent(envelope.data as unknown as MeetingEvent)
        if (items.length > 0) {
          store.appendActivity(sessionId, items)
        }
        return
      }

      if (envelope.type === 'activity_appended' && Array.isArray(envelope.data?.items)) {
        store.appendActivity(sessionId, envelope.data.items as ActivityItem[])
        return
      }

      if (envelope.type === 'snapshot_required') {
        store.setActivitySyncMeta(sessionId, { syncState: 'stale' })
        if (sessionId === useWorkspaceStore.getState().currentSessionId) {
          void syncCurrentSessionState(sessionId, { syncState: 'resyncing' })
        }
      }
    },
    [store, syncCurrentSessionState],
  )

  const { activitySocketState } = useActivitySocket({
    currentSessionId,
    onEvent: handleSocketEnvelope,
    onPoll: async (sessionId: string) => {
      await syncCurrentSessionState(sessionId)
    },
  })

  const markSessionModified = useCallback(
    (sessionId: string, taskInput: string, referenceText?: string, referenceImages?: string[]) => {
      if (!sessionId) return
      const nextWorkspace = useWorkspaceStore.getState().workspaceDraftsBySessionId[sessionId] ?? DEFAULT_WORKSPACE_DRAFT
      const title = deriveSessionTitle(
        taskInput,
        referenceText ?? nextWorkspace.referenceText,
        referenceImages ?? nextWorkspace.referenceImages,
      )
      store.setSessions(reorderSessions(useWorkspaceStore.getState().sessions, sessionId, title))
    },
    [store],
  )

  const appendOptimisticActivity = useCallback(
    async (
      kind: ActivityItem['kind'],
      body: string,
      options?: Partial<ActivityItem> & { sessionId?: string },
    ) => {
      const sessionId = options?.sessionId ?? useWorkspaceStore.getState().currentSessionId
      if (!sessionId) return
      const item = createActivityItem({
        kind,
        title: options?.title ?? (
          kind === 'user'
            ? 'You'
            : kind === 'llm'
              ? 'Agent'
              : kind === 'status'
                ? 'Status'
                : kind === 'feedback'
                  ? 'Feedback'
                  : kind === 'meeting_phase'
                    ? 'Phase'
                    : kind === 'meeting_step'
                      ? 'Step'
                      : 'System'
        ),
        body,
        collapsible: options?.collapsible,
        responseBody: options?.responseBody,
        validationError: options?.validationError,
        pairKey: options?.pairKey,
        pairLabel: options?.pairLabel,
        llmDirection: options?.llmDirection,
      })
      store.appendActivity(sessionId, [item])
      await persistActivity(sessionId, [item])
    },
    [persistActivity, store],
  )

  const handleTaskInputChange = useCallback(
    (value: string) => {
      if (!currentSessionId) return
      const nextWorkspace = { ...currentWorkspace, taskInput: value }
      store.upsertWorkspaceDraft(currentSessionId, { taskInput: value })
      markSessionModified(currentSessionId, value)
      void persistWorkspace(currentSessionId, nextWorkspace, value)
    },
    [currentSessionId, currentWorkspace, markSessionModified, persistWorkspace, store],
  )

  const handleReferenceTextChange = useCallback(
    (value: string) => {
      if (!currentSessionId) return
      const nextWorkspace = { ...currentWorkspace, referenceText: value }
      store.upsertWorkspaceDraft(currentSessionId, { referenceText: value })
      markSessionModified(currentSessionId, currentWorkspace.taskInput, value)
      void persistWorkspace(currentSessionId, nextWorkspace)
    },
    [currentSessionId, currentWorkspace, markSessionModified, persistWorkspace, store],
  )

  const handleReferenceImagePick = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      if (!currentSessionId) return
      const files = Array.from(event.target.files ?? [])
      const nextImages = files.map((file) => file.name)
      const nextWorkspace = { ...currentWorkspace, referenceImages: nextImages }
      store.upsertWorkspaceDraft(currentSessionId, { referenceImages: nextImages })
      markSessionModified(currentSessionId, currentWorkspace.taskInput, currentWorkspace.referenceText, nextImages)
      void persistWorkspace(currentSessionId, nextWorkspace)
    },
    [currentSessionId, currentWorkspace, markSessionModified, persistWorkspace, store],
  )

  const handleSaveSettings = useCallback(async () => {
    const latestSettings = useWorkspaceStore.getState().settings
    await appendOptimisticActivity('system', 'Saved environment settings for the next launch.')
    try {
      await api.saveRemoteSettings(latestSettings)
    } catch {
      await appendOptimisticActivity(
        'system',
        'Bridge unavailable. Settings were only kept in browser local storage.',
      )
    }
  }, [api, appendOptimisticActivity])

  const refreshAgentOrchestratorModels = useCallback(async (settings = useWorkspaceStore.getState().settings) => {
    if (!String(settings.agentOrchestratorUrl ?? '').trim()) {
      setAgentOrchestratorModels([])
      setAgentOrchestratorModelsError('Agent Orchestrator URL is empty.')
      return
    }
    setAgentOrchestratorModelsLoading(true)
    setAgentOrchestratorModelsError('')
    try {
      const result = await api.listAgentOrchestratorModels(settings)
      setAgentOrchestratorModels(result.models)
      setAgentOrchestratorModelsError(result.ok ? '' : result.message)
      if (!String(useWorkspaceStore.getState().settings.agentOrchestratorModel ?? '').trim() && result.models.length > 0) {
        store.setSettings((current) => ({
          ...current,
          agentOrchestratorModel: result.models[0].id,
        }))
      }
    } catch {
      setAgentOrchestratorModels([])
      setAgentOrchestratorModelsError('Bridge unavailable. Agent Orchestrator models could not be loaded.')
    } finally {
      setAgentOrchestratorModelsLoading(false)
    }
  }, [api, store])

  const verifyAgentOrchestratorSettings = useCallback(async (settings: typeof store.settings) => {
    store.setAgentOrchestratorVerifying(true)
    try {
      const result = await api.verifyAgentOrchestrator(settings)
      store.setAgentOrchestratorStatus(result)
      return result
    } catch {
      const fallbackResult = {
        name: 'agent_orchestrator_health',
        ok: false,
        message: 'Bridge unavailable. Agent Orchestrator verification could not be completed.',
      } satisfies NonNullable<typeof store.agentOrchestratorStatus>
      store.setAgentOrchestratorStatus(fallbackResult)
      return fallbackResult
    } finally {
      store.setAgentOrchestratorVerifying(false)
    }
  }, [api, store])

  const handleVerifyAgentOrchestrator = useCallback(async () => {
    await refreshAgentOrchestratorModels(store.settings)
    const result = await verifyAgentOrchestratorSettings(store.settings)
    await appendOptimisticActivity(
      'system',
      result.ok
        ? 'Agent Orchestrator verification passed.'
        : 'Agent Orchestrator verification found an issue.',
    )
  }, [appendOptimisticActivity, refreshAgentOrchestratorModels, store.settings, verifyAgentOrchestratorSettings])

  const autoVerifyAgentOrchestratorOnSessionEntry = useCallback(async () => {
    await verifyAgentOrchestratorSettings(useWorkspaceStore.getState().settings)
  }, [verifyAgentOrchestratorSettings])

  useAutoVerifyAgentOrchestratorOnSessionEntry({
    currentSessionId,
    agentOrchestratorUrl: store.settings.agentOrchestratorUrl,
    onVerify: autoVerifyAgentOrchestratorOnSessionEntry,
  })

  const handleRunDiagnostics = useCallback(async () => {
    if (!currentSessionId) return
    store.setLiveDiagnosticsRunning(true)
    try {
      const diagnostics = await api.runLiveDiagnostics(currentSessionId, store.settings)
      store.setLiveDiagnostics(diagnostics)
      await appendOptimisticActivity(
        'system',
        diagnostics.ok
          ? 'Live diagnostics passed for Agent Orchestrator and Blender MCP.'
          : 'Live diagnostics found an issue with the current environment.',
      )
    } finally {
      store.setLiveDiagnosticsRunning(false)
    }
  }, [api, appendOptimisticActivity, currentSessionId, store])

  const handleSettingsUpdate = useCallback(
    (updater: typeof store.settings | ((prev: typeof store.settings) => typeof store.settings)) => {
      store.setSettings(updater)
    },
    [store],
  )

  const handleStartRun = useCallback(async () => {
    if (!currentSessionId) return
    if (!canStartRun) {
      if (startBlockedReason) {
        await appendOptimisticActivity('system', startBlockedReason)
      }
      return
    }
    setComposerExpanded(false)
    const currentWorkspaceValue = useWorkspaceStore.getState().workspaceDraftsBySessionId[currentSessionId] ?? DEFAULT_WORKSPACE_DRAFT
    await persistWorkspace(currentSessionId, currentWorkspaceValue, currentWorkspaceValue.taskInput)
    await appendOptimisticActivity('user', currentWorkspaceValue.taskInput)
    markSessionModified(currentSessionId, currentWorkspaceValue.taskInput)
    const result = await api.startRun(currentSessionId, store.settings, currentWorkspaceValue)
    store.setRunStatus(currentSessionId, result.run_status)
    if (!result.started && result.error_message) {
      await appendOptimisticActivity('system', String(result.error_message))
    }
  }, [
    api,
    appendOptimisticActivity,
    canStartRun,
    currentSessionId,
    markSessionModified,
    persistWorkspace,
    startBlockedReason,
    store,
  ])

  const handleStopRun = useCallback(async () => {
    if (!currentSessionId) return
    const payload = await api.stopRun(currentSessionId)
    store.setRunStatus(currentSessionId, payload.run_status)
    await appendOptimisticActivity(
      'system',
      payload.stopped
        ? `Stop requested for session ${currentSessionId}.`
        : String(payload.reason || 'Stop could not be completed.'),
    )
    const consoleLog = await api.fetchConsoleLog(currentSessionId)
    store.setConsoleLog(currentSessionId, consoleLog)
  }, [api, appendOptimisticActivity, currentSessionId, store])

  const handleRetryRun = useCallback(async (retryCount: number) => {
    if (!currentSessionId) return
    const payload = await api.retryRun(currentSessionId, retryCount)
    store.setRunStatus(currentSessionId, payload.run_status)
    store.setRetryPrompt(currentSessionId, {
      ...DEFAULT_RETRY_PROMPT,
      session_id: currentSessionId,
      decision_state: 'retrying',
      auto_retrying: true,
      attempt_index: payload.run_status.attempt_index,
      next_attempt_index: (payload.run_status.attempt_index ?? 0) + 1,
      remaining_retries: Math.max(0, retryCount - 1),
      show: false,
    })
    await appendOptimisticActivity(
      'system',
      payload.started
        ? `Retry started with ${retryCount} attempts.`
        : String(payload.error_message || 'Retry request could not be started.'),
    )
  }, [api, appendOptimisticActivity, currentSessionId, store])

  const handleStopRetryPrompt = useCallback(async () => {
    if (!currentSessionId) return
    await api.clearRetryPrompt(currentSessionId)
    store.setRetryPrompt(currentSessionId, { ...DEFAULT_RETRY_PROMPT, session_id: currentSessionId })
    await appendOptimisticActivity('system', 'Auto retry has been stopped.')
  }, [api, appendOptimisticActivity, currentSessionId, store])

  const handleSelectSession = useCallback(
    (sessionId: string) => {
      if (sessionId === currentSessionId) return
      void activateSession(sessionId)
    },
    [activateSession, currentSessionId],
  )

  const handleNewSession = useCallback(async () => {
    const result = await api.createSession()
    const sessionId = result.session_id
    store.setSessions(reorderSessions(useWorkspaceStore.getState().sessions, sessionId, 'New modeling session'))
    store.upsertWorkspaceDraft(sessionId, DEFAULT_WORKSPACE_DRAFT)
    store.replaceActivity(sessionId, [])
    store.resetSessionRuntimeState(sessionId)
    await activateSession(sessionId, { clearExpanded: true })
  }, [activateSession, api, store])

  const confirmDeleteSession = useCallback(async () => {
    if (!pendingDeleteSessionId) return
    const deletingCurrentSession = pendingDeleteSessionId === useWorkspaceStore.getState().currentSessionId
    await api.deleteSession(pendingDeleteSessionId)
    store.removeSession(pendingDeleteSessionId)
    const remainingSessions = useWorkspaceStore.getState().sessions
    const nextSessionId = deletingCurrentSession ? remainingSessions[0]?.id ?? '' : useWorkspaceStore.getState().currentSessionId
    setPendingDeleteSessionId('')
    if (!deletingCurrentSession) {
      return
    }
    if (nextSessionId) {
      await activateSession(nextSessionId, { clearExpanded: false })
      return
    }
    sessionActivationRequestRef.current += 1
    setExpandedActivityIds([])
    store.setCurrentSessionId('')
  }, [activateSession, api, pendingDeleteSessionId, setExpandedActivityIds, store])

  const toggleBatchDeleteMode = useCallback(() => {
    setBatchDeleteMode((enabled) => {
      const nextEnabled = !enabled
      if (!nextEnabled) {
        setBatchDeleteSelectedIds([])
        setBatchDeleteConfirmOpen(false)
      }
      return nextEnabled
    })
  }, [])

  const toggleBatchDeleteSelection = useCallback((sessionId: string, selected: boolean) => {
    setBatchDeleteSelectedIds((current) => {
      if (selected) {
        return current.includes(sessionId) ? current : [...current, sessionId]
      }
      return current.filter((id) => id !== sessionId)
    })
  }, [])

  const requestBatchDelete = useCallback(() => {
    const availableIds = new Set(useWorkspaceStore.getState().sessions.map((session) => session.id))
    const selectedIds = batchDeleteSelectedIds.filter((sessionId) => availableIds.has(sessionId))
    if (selectedIds.length === 0) return
    setBatchDeleteSelectedIds(selectedIds)
    setBatchDeleteConfirmOpen(true)
  }, [batchDeleteSelectedIds])

  const confirmBatchDeleteSessions = useCallback(async () => {
    const selectedIds = batchDeleteSelectedIds.filter((sessionId) =>
      useWorkspaceStore.getState().sessions.some((session) => session.id === sessionId),
    )
    if (selectedIds.length === 0) {
      setBatchDeleteConfirmOpen(false)
      return
    }

    const currentBeforeDelete = useWorkspaceStore.getState().currentSessionId
    const deletingCurrentSession = selectedIds.includes(currentBeforeDelete)
    for (const sessionId of selectedIds) {
      await api.deleteSession(sessionId)
      store.removeSession(sessionId)
    }

    const remainingSessions = useWorkspaceStore.getState().sessions
    const nextSessionId = deletingCurrentSession
      ? remainingSessions[0]?.id ?? ''
      : useWorkspaceStore.getState().currentSessionId

    setBatchDeleteConfirmOpen(false)
    setBatchDeleteMode(false)
    setBatchDeleteSelectedIds([])
    setPendingDeleteSessionId('')

    if (!deletingCurrentSession) {
      return
    }
    if (nextSessionId) {
      await activateSession(nextSessionId, { clearExpanded: false })
      return
    }
    sessionActivationRequestRef.current += 1
    setExpandedActivityIds([])
    store.setCurrentSessionId('')
  }, [activateSession, api, batchDeleteSelectedIds, setExpandedActivityIds, store])

  const sidebarModel = useMemo(
    () => ({
      sessions: store.sessions,
      currentSessionId,
      settingsOpen,
      sidebarOpen,
      batchDeleteMode,
      batchDeleteSelectedIds,
    }),
    [batchDeleteMode, batchDeleteSelectedIds, currentSessionId, settingsOpen, sidebarOpen, store.sessions],
  )

  const composerModel = useMemo(
    () => ({
      currentSession,
      currentSessionId,
      taskInput: currentWorkspace.taskInput,
      referenceText: currentWorkspace.referenceText,
      referenceImages: currentWorkspace.referenceImages,
      canStartRun,
      canStopRun,
      startBlockedReason,
      liveDiagnosticsRunning: store.liveDiagnosticsRunning,
      settingsOpen,
      progressStage: currentProgress.stage,
      workflowStatus: currentRunStatus.workflow_status,
      activityState: activitySocketState,
      syncState: currentActivityMeta?.syncState ?? 'idle',
      agentOrchestratorReady,
      mcpState: store.mcpStatus.state,
      composerExpanded,
    }),
    [
      activitySocketState,
      canStartRun,
      canStopRun,
      composerExpanded,
      currentProgress.stage,
      currentRunStatus.workflow_status,
      currentSession,
      currentSessionId,
      currentWorkspace.referenceImages,
      currentWorkspace.referenceText,
      currentWorkspace.taskInput,
      currentActivityMeta?.syncState,
      agentOrchestratorReady,
      settingsOpen,
      startBlockedReason,
      store.liveDiagnosticsRunning,
      store.mcpStatus.state,
    ],
  )

  const activityModel = useMemo(
    () => ({
      activity: currentActivity,
      expandedActivityIds,
      retryPrompt: currentRetryPrompt,
      runStatus: currentRunStatus,
      currentSessionId,
      syncState: currentActivityMeta?.syncState ?? 'idle',
    }),
    [currentActivity, currentRetryPrompt, currentRunStatus, currentSessionId, currentActivityMeta?.syncState, expandedActivityIds],
  )

  const settingsModel = useMemo(
    () => ({
      open: settingsOpen,
      settings: store.settings,
      mcpStatus: store.mcpStatus,
      agentOrchestratorVerifying: store.agentOrchestratorVerifying,
      agentOrchestratorStatus: store.agentOrchestratorStatus,
      agentOrchestratorModels,
      agentOrchestratorModelsLoading,
      agentOrchestratorModelsError,
    }),
    [
      agentOrchestratorModels,
      agentOrchestratorModelsError,
      agentOrchestratorModelsLoading,
      settingsOpen,
      store.agentOrchestratorStatus,
      store.agentOrchestratorVerifying,
      store.mcpStatus,
      store.settings,
    ],
  )

  return {
      state: {
        hasSessions,
        initializationState,
        pendingDeleteSessionId,
        batchDeleteConfirmOpen,
        selectedTask,
        selectedInspectorTitle,
        latestInspectorCapturePath,
        inspectorSelectionKind,
        currentProgress,
        inspectorBlocks,
        currentRunStatus,
      currentConsoleLog,
      currentMcpToolCalls,
      currentActivityMeta,
    },
    models: {
      sidebar: sidebarModel,
      composer: composerModel,
      activity: activityModel,
      settings: settingsModel,
        inspector: {
          open: inspectorOpen,
          progress: currentProgress,
          selectedTask,
          selectedTitle: selectedInspectorTitle,
          latestCapturePath: latestInspectorCapturePath,
          selectionKind: inspectorSelectionKind,
          inspectorBlocks,
        },
      runtime: {
        open: runtimeOpen,
        runStatus: currentRunStatus,
        mcpStatus: store.mcpStatus,
        consoleLog: currentConsoleLog,
        mcpToolCalls: currentMcpToolCalls,
      },
      deleteModal: {
        open: Boolean(pendingDeleteSessionId) || batchDeleteConfirmOpen,
        sessionTitle: batchDeleteConfirmOpen
          ? `${batchDeleteSelectedIds.length} selected sessions`
          : store.sessions.find((session) => session.id === pendingDeleteSessionId)?.title || pendingDeleteSessionId,
        eyebrow: batchDeleteConfirmOpen ? 'Batch Delete Sessions' : 'Delete Session',
        description: batchDeleteConfirmOpen
          ? 'This removes all selected local session progress files. The workspace will move to the next remaining session when needed.'
          : 'This removes the local session progress file and keeps the current UI workspace focused on the remaining sessions.',
        confirmLabel: batchDeleteConfirmOpen ? 'Delete Selected' : 'Delete',
      },
    },
    actions: {
      sidebar: {
        onSelectSession: handleSelectSession,
        onRequestDeleteSession: setPendingDeleteSessionId,
        onNewSession: () => void handleNewSession(),
        onToggleSettings: () => setSettingsOpen((value) => !value),
        onCloseSidebar: () => setSidebarOpen(false),
        onOpenSidebar: () => setSidebarOpen(true),
        onToggleBatchDeleteMode: toggleBatchDeleteMode,
        onToggleBatchDeleteSelection: toggleBatchDeleteSelection,
        onRequestBatchDelete: requestBatchDelete,
      },
      composer: {
        onToggleComposer: () => setComposerExpanded((value) => !value),
        onTaskInputChange: handleTaskInputChange,
        onReferenceTextChange: handleReferenceTextChange,
        onReferenceImagePick: handleReferenceImagePick,
        onStartRun: () => void handleStartRun(),
        onStopRun: () => void handleStopRun(),
        onRunLiveDiagnostics: () => void handleRunDiagnostics(),
        onToggleSettings: () => setSettingsOpen((value) => !value),
        onToggleInspector: () => setInspectorOpen((value) => !value),
        onToggleRuntime: () => setRuntimeOpen((value) => !value),
      },
      activity: {
        onToggleExpand: toggleExpandedActivityId,
        onRetry: (count: number) => void handleRetryRun(count),
        onStopRetry: () => void handleStopRetryPrompt(),
      },
      settings: {
        onSettingsUpdate: handleSettingsUpdate,
        onClose: () => setSettingsOpen(false),
        onVerifyAgentOrchestrator: () => void handleVerifyAgentOrchestrator(),
        onRefreshAgentOrchestratorModels: () => void refreshAgentOrchestratorModels(),
        onSaveSettings: () => void handleSaveSettings(),
      },
      inspector: {
        onClose: () => setInspectorOpen(false),
      },
      runtime: {
        onClose: () => setRuntimeOpen(false),
      },
      deleteModal: {
        onCancel: () => {
          setPendingDeleteSessionId('')
          setBatchDeleteConfirmOpen(false)
        },
        onConfirm: () => {
          if (batchDeleteConfirmOpen) {
            void confirmBatchDeleteSessions()
            return
          }
          void confirmDeleteSession()
        },
      },
    },
  }
}
