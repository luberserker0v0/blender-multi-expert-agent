import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import {
  DEFAULT_ACTIVITY_SYNC_META,
  DEFAULT_MCP_STATUS,
  DEFAULT_RETRY_PROMPT,
  DEFAULT_RUN_STATUS,
  DEFAULT_WORKSPACE_DRAFT,
} from '../constants'
import type {
  ActivityItem,
  ActivitySyncMeta,
  LiveDiagnosticsResult,
  AgentOrchestratorResult,
  McpConnectionStatus,
  McpToolCallRecord,
  MultiStageProgressSnapshot,
  RetryPromptState,
  RunStatus,
  SavedSettings,
  SessionStateSnapshot,
  SessionSummary,
  WorkspaceDraft,
} from '../types'
import { createEmptyProgress } from '../utils/normalizers'

export interface WorkspaceStoreState {
  settings: SavedSettings
  sessions: SessionSummary[]
  currentSessionId: string
  workspaceDraftsBySessionId: Record<string, WorkspaceDraft>
  activityBySessionId: Record<string, ActivityItem[]>
  activitySyncMetaBySessionId: Record<string, ActivitySyncMeta>
  progressBySessionId: Record<string, MultiStageProgressSnapshot>
  runStatusBySessionId: Record<string, RunStatus>
  retryPromptBySessionId: Record<string, RetryPromptState>
  consoleLogBySessionId: Record<string, string>
  mcpToolCallsBySessionId: Record<string, McpToolCallRecord[]>
  mcpStatus: McpConnectionStatus
  liveDiagnostics: LiveDiagnosticsResult | null
  agentOrchestratorStatus: AgentOrchestratorResult | null
  liveDiagnosticsRunning: boolean
  agentOrchestratorVerifying: boolean
}

export interface WorkspaceStoreActions {
  setSettings: (settings: SavedSettings | ((current: SavedSettings) => SavedSettings)) => void
  setSessions: (sessions: SessionSummary[]) => void
  setCurrentSessionId: (sessionId: string) => void
  upsertWorkspaceDraft: (sessionId: string, patch: Partial<WorkspaceDraft>) => void
  replaceActivity: (sessionId: string, items: ActivityItem[]) => void
  appendActivity: (sessionId: string, items: ActivityItem[]) => void
  setActivitySyncMeta: (sessionId: string, meta: Partial<ActivitySyncMeta>) => void
  setProgress: (sessionId: string, progress: MultiStageProgressSnapshot) => void
  setRunStatus: (sessionId: string, runStatus: RunStatus) => void
  setRetryPrompt: (sessionId: string, retryPrompt: RetryPromptState) => void
  setConsoleLog: (sessionId: string, consoleLog: string) => void
  setMcpToolCalls: (sessionId: string, toolCalls: McpToolCallRecord[]) => void
  setMcpStatus: (status: McpConnectionStatus) => void
  setLiveDiagnostics: (value: LiveDiagnosticsResult | null) => void
  setAgentOrchestratorStatus: (value: AgentOrchestratorResult | null) => void
  setLiveDiagnosticsRunning: (value: boolean) => void
  setAgentOrchestratorVerifying: (value: boolean) => void
  hydrateSessionSnapshot: (snapshot: SessionStateSnapshot) => void
  resetSessionRuntimeState: (sessionId: string) => void
  removeSession: (sessionId: string) => void
}

interface WorkspaceStore extends WorkspaceStoreState, WorkspaceStoreActions {}

function dedupeActivityItems(existing: ActivityItem[], incoming: ActivityItem[]) {
  if (incoming.length === 0) return existing
  const seenIds = new Set(existing.map((item) => item.id).filter(Boolean))
  const dedupedIncoming = incoming.filter((item) => {
    if (!item.id) {
      return true
    }
    if (seenIds.has(item.id)) {
      return false
    }
    seenIds.add(item.id)
    return true
  })
  return dedupedIncoming.length > 0 ? [...existing, ...dedupedIncoming] : existing
}

function ensureWorkspaceDraft(current: Record<string, WorkspaceDraft>, sessionId: string) {
  return current[sessionId] ?? { ...DEFAULT_WORKSPACE_DRAFT }
}

function ensureSyncMeta(current: Record<string, ActivitySyncMeta>, sessionId: string) {
  return current[sessionId] ?? {
    ...DEFAULT_ACTIVITY_SYNC_META,
    markers: {
      ...DEFAULT_ACTIVITY_SYNC_META.markers,
      seenPromptEventIds: [],
      seenConclusionIds: [],
    },
  }
}

export function createInitialWorkspaceStoreState(defaultSettings: SavedSettings): WorkspaceStoreState {
  return {
    settings: defaultSettings,
    sessions: [],
    currentSessionId: '',
    workspaceDraftsBySessionId: {},
    activityBySessionId: {},
    activitySyncMetaBySessionId: {},
    progressBySessionId: {},
    runStatusBySessionId: {},
    retryPromptBySessionId: {},
    consoleLogBySessionId: {},
    mcpToolCallsBySessionId: {},
    mcpStatus: DEFAULT_MCP_STATUS,
    liveDiagnostics: null,
    agentOrchestratorStatus: null,
    liveDiagnosticsRunning: false,
    agentOrchestratorVerifying: false,
  }
}

export function createWorkspaceStore(defaultSettings: SavedSettings) {
  return create<WorkspaceStore>()(
    persist(
      (set) => ({
        ...createInitialWorkspaceStoreState(defaultSettings),
        setSettings: (settings) =>
          set((state) => ({
            settings: typeof settings === 'function' ? settings(state.settings) : settings,
          })),
        setSessions: (sessions) => set({ sessions }),
        setCurrentSessionId: (currentSessionId) => set({ currentSessionId }),
        upsertWorkspaceDraft: (sessionId, patch) =>
          set((state) => ({
            workspaceDraftsBySessionId: {
              ...state.workspaceDraftsBySessionId,
              [sessionId]: {
                ...ensureWorkspaceDraft(state.workspaceDraftsBySessionId, sessionId),
                ...patch,
              },
            },
          })),
        replaceActivity: (sessionId, items) =>
          set((state) => ({
            activityBySessionId: { ...state.activityBySessionId, [sessionId]: items },
          })),
        appendActivity: (sessionId, items) =>
          set((state) => ({
            activityBySessionId: {
              ...state.activityBySessionId,
              [sessionId]: dedupeActivityItems(state.activityBySessionId[sessionId] ?? [], items),
            },
          })),
        setActivitySyncMeta: (sessionId, meta) =>
          set((state) => ({
            activitySyncMetaBySessionId: {
              ...state.activitySyncMetaBySessionId,
              [sessionId]: {
                ...ensureSyncMeta(state.activitySyncMetaBySessionId, sessionId),
                ...meta,
                markers: {
                  ...ensureSyncMeta(state.activitySyncMetaBySessionId, sessionId).markers,
                  ...(meta.markers ?? {}),
                },
              },
            },
          })),
        setProgress: (sessionId, progress) =>
          set((state) => ({
            progressBySessionId: { ...state.progressBySessionId, [sessionId]: progress },
          })),
        setRunStatus: (sessionId, runStatus) =>
          set((state) => ({
            runStatusBySessionId: { ...state.runStatusBySessionId, [sessionId]: runStatus },
          })),
        setRetryPrompt: (sessionId, retryPrompt) =>
          set((state) => ({
            retryPromptBySessionId: { ...state.retryPromptBySessionId, [sessionId]: retryPrompt },
          })),
        setConsoleLog: (sessionId, consoleLog) =>
          set((state) => ({
            consoleLogBySessionId: { ...state.consoleLogBySessionId, [sessionId]: consoleLog },
          })),
        setMcpToolCalls: (sessionId, mcpToolCalls) =>
          set((state) => ({
            mcpToolCallsBySessionId: { ...state.mcpToolCallsBySessionId, [sessionId]: mcpToolCalls },
          })),
        setMcpStatus: (mcpStatus) => set({ mcpStatus }),
        setLiveDiagnostics: (liveDiagnostics) => set({ liveDiagnostics }),
        setAgentOrchestratorStatus: (agentOrchestratorStatus) => set({ agentOrchestratorStatus }),
        setLiveDiagnosticsRunning: (liveDiagnosticsRunning) => set({ liveDiagnosticsRunning }),
        setAgentOrchestratorVerifying: (agentOrchestratorVerifying) => set({ agentOrchestratorVerifying }),
        hydrateSessionSnapshot: (snapshot) =>
          set((state) => ({
            workspaceDraftsBySessionId: {
              ...state.workspaceDraftsBySessionId,
              [snapshot.session_id]: snapshot.workspace,
            },
            activityBySessionId: {
              ...state.activityBySessionId,
              [snapshot.session_id]: snapshot.activity,
            },
            activitySyncMetaBySessionId: {
              ...state.activitySyncMetaBySessionId,
              [snapshot.session_id]: {
                ...ensureSyncMeta(state.activitySyncMetaBySessionId, snapshot.session_id),
                lastServerCursor: snapshot.server_cursor,
                syncState: 'live',
              },
            },
            progressBySessionId: {
              ...state.progressBySessionId,
              [snapshot.session_id]: snapshot.progress ?? createEmptyProgress(),
            },
            runStatusBySessionId: {
              ...state.runStatusBySessionId,
              [snapshot.session_id]: snapshot.run_status,
            },
            retryPromptBySessionId: {
              ...state.retryPromptBySessionId,
              [snapshot.session_id]: snapshot.retry_prompt,
            },
            consoleLogBySessionId: {
              ...state.consoleLogBySessionId,
              [snapshot.session_id]: snapshot.console_log,
            },
            mcpToolCallsBySessionId: {
              ...state.mcpToolCallsBySessionId,
              [snapshot.session_id]: snapshot.mcp_tool_calls,
            },
            mcpStatus: snapshot.mcp_status,
          })),
        resetSessionRuntimeState: (sessionId) =>
          set((state) => ({
            progressBySessionId: { ...state.progressBySessionId, [sessionId]: createEmptyProgress() },
            runStatusBySessionId: { ...state.runStatusBySessionId, [sessionId]: { ...DEFAULT_RUN_STATUS, session_id: sessionId } },
            retryPromptBySessionId: { ...state.retryPromptBySessionId, [sessionId]: { ...DEFAULT_RETRY_PROMPT, session_id: sessionId } },
            consoleLogBySessionId: { ...state.consoleLogBySessionId, [sessionId]: '' },
            mcpToolCallsBySessionId: { ...state.mcpToolCallsBySessionId, [sessionId]: [] },
            activitySyncMetaBySessionId: {
              ...state.activitySyncMetaBySessionId,
              [sessionId]: ensureSyncMeta(state.activitySyncMetaBySessionId, sessionId),
            },
          })),
        removeSession: (sessionId) =>
          set((state) => {
            const workspaceDraftsBySessionId = { ...state.workspaceDraftsBySessionId }
            const activityBySessionId = { ...state.activityBySessionId }
            const activitySyncMetaBySessionId = { ...state.activitySyncMetaBySessionId }
            const progressBySessionId = { ...state.progressBySessionId }
            const runStatusBySessionId = { ...state.runStatusBySessionId }
            const retryPromptBySessionId = { ...state.retryPromptBySessionId }
            const consoleLogBySessionId = { ...state.consoleLogBySessionId }
            const mcpToolCallsBySessionId = { ...state.mcpToolCallsBySessionId }
            delete workspaceDraftsBySessionId[sessionId]
            delete activityBySessionId[sessionId]
            delete activitySyncMetaBySessionId[sessionId]
            delete progressBySessionId[sessionId]
            delete runStatusBySessionId[sessionId]
            delete retryPromptBySessionId[sessionId]
            delete consoleLogBySessionId[sessionId]
            delete mcpToolCallsBySessionId[sessionId]
            return {
              sessions: state.sessions.filter((session) => session.id !== sessionId),
              workspaceDraftsBySessionId,
              activityBySessionId,
              activitySyncMetaBySessionId,
              progressBySessionId,
              runStatusBySessionId,
              retryPromptBySessionId,
              consoleLogBySessionId,
              mcpToolCallsBySessionId,
            }
          }),
      }),
      {
        name: 'ai3d-react-ui-store',
        storage: createJSONStorage(() => window.localStorage),
        partialize: (state) => ({
          settings: state.settings,
          sessions: state.sessions,
          currentSessionId: state.currentSessionId,
          workspaceDraftsBySessionId: state.workspaceDraftsBySessionId,
          activityBySessionId: state.activityBySessionId,
          activitySyncMetaBySessionId: state.activitySyncMetaBySessionId,
        }),
      },
    ),
  )
}
