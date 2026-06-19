import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useWorkspaceController } from './useWorkspaceController'
import { useWorkspaceStore } from '../store'
import { createInitialWorkspaceStoreState } from '../store/useWorkspaceStore'
import { defaultSettings } from '../data/sampleSession'
import type {
  ActivityEventEnvelope,
  ActivityItem,
  BootstrapResponse,
  MeetingEvent,
  SessionStateSnapshot,
} from '../types'
import { DEFAULT_MCP_STATUS, DEFAULT_RETRY_PROMPT, DEFAULT_RUN_STATUS, DEFAULT_WORKSPACE_DRAFT } from '../constants'
import { createEmptyProgress } from '../utils/normalizers'

const mockApi = {
  appendActivity: vi.fn(),
  bootstrap: vi.fn(),
  clearRetryPrompt: vi.fn(),
  createSession: vi.fn(),
  deleteSession: vi.fn(),
  fetchConsoleLog: vi.fn(),
  fetchMcpStatus: vi.fn(),
  fetchMcpToolCalls: vi.fn(),
  fetchRunStatus: vi.fn(),
  getActivitySnapshot: vi.fn(),
  getSessionState: vi.fn(),
  retryRun: vi.fn(),
  runLiveDiagnostics: vi.fn(),
  saveRemoteSettings: vi.fn(),
  saveWorkspace: vi.fn(),
  setCurrentSession: vi.fn(),
  startRun: vi.fn(),
  stopRun: vi.fn(),
  syncBlenderMcp: vi.fn(),
  verifyAgentOrchestrator: vi.fn(),
}

let capturedSocketConfig:
  | {
      currentSessionId: string
      onEvent: (envelope: ActivityEventEnvelope) => void
      onPoll: (sessionId: string) => Promise<void>
    }
  | undefined

vi.mock('./useBridgeApi', () => ({
  useBridgeApi: () => mockApi,
}))

vi.mock('./useActivitySocket', () => ({
  default: (config: typeof capturedSocketConfig) => {
    capturedSocketConfig = config
    return { activitySocketState: 'live' as const }
  },
}))

vi.mock('./useAutoVerifyAgentOrchestratorOnSessionEntry', () => ({
  useAutoVerifyAgentOrchestratorOnSessionEntry: () => undefined,
}))

function createSessionSnapshot(
  overrides: Partial<SessionStateSnapshot> = {},
  activity: ActivityItem[] = [],
): SessionStateSnapshot {
  return {
    session_id: 'session-1',
    workspace: { ...DEFAULT_WORKSPACE_DRAFT },
    activity,
    progress: createEmptyProgress(),
    run_status: { ...DEFAULT_RUN_STATUS, session_id: 'session-1' },
    retry_prompt: { ...DEFAULT_RETRY_PROMPT, session_id: 'session-1' },
    console_log: '',
    mcp_tool_calls: [],
    mcp_status: { ...DEFAULT_MCP_STATUS, state: 'connected', message: 'connected' },
    server_cursor: 'session-1:1',
    snapshot_generated_at: Date.now(),
    ...overrides,
  }
}

function createBootstrapResponse(): BootstrapResponse {
  return {
    sessions: [{ id: 'session-1', title: 'Session One', updatedAt: 'just now' }],
    current_session_id: 'session-1',
    settings: defaultSettings,
    mcp_status: { ...DEFAULT_MCP_STATUS, state: 'connected', message: 'connected' },
  }
}

function createProgressSnapshotWithDerivedItems() {
  return {
    ...createEmptyProgress(),
    status: 'running',
    stage: 'planning',
    stage_status: 'completed',
    part_tasks: [
      {
        task_id: 'task-1',
        title: 'Chair Back',
        object_name: 'chair_back',
        status: 'pending',
        current_round: 0,
        approved: false,
        hidden_after_approval: false,
        rounds: [],
      },
    ],
  }
}

describe('useWorkspaceController activity consistency', () => {
  beforeEach(() => {
    capturedSocketConfig = undefined
    vi.clearAllMocks()
    window.localStorage.clear()
    useWorkspaceStore.setState(createInitialWorkspaceStoreState(defaultSettings))
    mockApi.bootstrap.mockResolvedValue(createBootstrapResponse())
    mockApi.getSessionState.mockResolvedValue(
      createSessionSnapshot({
        progress: createProgressSnapshotWithDerivedItems(),
      }),
    )
    mockApi.setCurrentSession.mockResolvedValue({ ok: true })
    mockApi.verifyAgentOrchestrator.mockResolvedValue({
      name: 'agent_orchestrator_health',
      ok: true,
      message: 'ready',
    })
  })

  it('keeps progress-derived activity suppressed when snapshot_required replays the same snapshot', async () => {
    renderHook(() => useWorkspaceController())

    await waitFor(() => {
      expect(useWorkspaceStore.getState().currentSessionId).toBe('session-1')
      expect(useWorkspaceStore.getState().activityBySessionId['session-1']).toHaveLength(0)
    })

    await act(async () => {
      capturedSocketConfig?.onEvent({
        type: 'snapshot_required',
        session_id: 'session-1',
        event_id: 'event-1',
        sequence: 1,
        server_cursor: 'session-1:1',
      })
      await Promise.resolve()
    })

    await waitFor(() => {
      expect(mockApi.getSessionState).toHaveBeenCalledTimes(2)
      expect(useWorkspaceStore.getState().activityBySessionId['session-1']).toHaveLength(0)
    })
  })

  it('keeps appended activity consistent after a later snapshot hydrate', async () => {
    const appended: ActivityItem = {
      id: 'persisted-1',
      kind: 'system',
      title: 'System',
      body: 'Persisted activity item',
      timestamp: '09:41',
    }
    let snapshot = createSessionSnapshot({}, [])
    mockApi.getSessionState.mockImplementation(async () => snapshot)

    renderHook(() => useWorkspaceController())

    await waitFor(() => {
      expect(useWorkspaceStore.getState().currentSessionId).toBe('session-1')
    })

    act(() => {
      capturedSocketConfig?.onEvent({
        type: 'activity_appended',
        session_id: 'session-1',
        event_id: 'event-2',
        sequence: 2,
        server_cursor: 'session-1:2',
        data: { items: [appended] },
      })
    })

    expect(useWorkspaceStore.getState().activityBySessionId['session-1']).toEqual(
      expect.arrayContaining([appended]),
    )
    expect(useWorkspaceStore.getState().activityBySessionId['session-1']).toHaveLength(1)

    snapshot = createSessionSnapshot({}, [appended])
    await act(async () => {
      capturedSocketConfig?.onEvent({
        type: 'snapshot_required',
        session_id: 'session-1',
        event_id: 'event-3',
        sequence: 3,
        server_cursor: 'session-1:3',
      })
      await Promise.resolve()
    })

    await waitFor(() => {
      expect(useWorkspaceStore.getState().activityBySessionId['session-1']).toEqual(
        expect.arrayContaining([appended]),
      )
      expect(useWorkspaceStore.getState().activityBySessionId['session-1']).toHaveLength(1)
    })
  })

  it('dedupes repeated activity_appended items by id before a later snapshot hydrate', async () => {
    const appended: ActivityItem = {
      id: 'persisted-1',
      kind: 'system',
      title: 'System',
      body: 'Persisted activity item',
      timestamp: '09:41',
    }

    renderHook(() => useWorkspaceController())

    await waitFor(() => {
      expect(useWorkspaceStore.getState().currentSessionId).toBe('session-1')
    })

    act(() => {
      capturedSocketConfig?.onEvent({
        type: 'activity_appended',
        session_id: 'session-1',
        event_id: 'event-2',
        sequence: 2,
        server_cursor: 'session-1:2',
        data: { items: [appended] },
      })
      capturedSocketConfig?.onEvent({
        type: 'activity_appended',
        session_id: 'session-1',
        event_id: 'event-3',
        sequence: 3,
        server_cursor: 'session-1:3',
        data: { items: [appended] },
      })
    })

    const persistedItems = useWorkspaceStore
      .getState()
      .activityBySessionId['session-1']
      .filter((item) => item.id === 'persisted-1')

    expect(persistedItems).toHaveLength(1)
  })

  it('updates only the matching session slice for non-current session websocket events', async () => {
    renderHook(() => useWorkspaceController())

    await waitFor(() => {
      expect(useWorkspaceStore.getState().currentSessionId).toBe('session-1')
    })

    const event: MeetingEvent = {
      schema_version: 1,
      event_id: 'meeting-1',
      phase: 'design',
      kind: 'proposal',
      summary: 'Narrow backrest',
      full_content: 'Proposal: Use a narrow backrest for the chair.',
      message: 'The designer proposes a narrow backrest.',
      content_preview: 'Narrow backrest',
      speaker: 'designer',
      role: 'owner',
      round: 1,
      timestamp: '09:40',
    }

    act(() => {
      capturedSocketConfig?.onEvent({
        type: 'meeting_event',
        session_id: 'session-2',
        event_id: 'event-4',
        sequence: 4,
        server_cursor: 'session-2:1',
        data: event as unknown as Record<string, unknown>,
      })
    })

    expect(useWorkspaceStore.getState().activityBySessionId['session-2']).toHaveLength(1)
    expect(useWorkspaceStore.getState().activityBySessionId['session-2'][0].body).toBe('Narrow backrest')
    expect(useWorkspaceStore.getState().currentSessionId).toBe('session-1')
    expect(useWorkspaceStore.getState().activityBySessionId['session-1']).toHaveLength(0)
  })

  it('does not append idle waiting-for-prompt as the latest activity after a resync', async () => {
    const appended: ActivityItem = {
      id: 'meeting-1',
      kind: 'system',
      title: 'System',
      body: 'Bridge emitted a new activity item.',
      timestamp: '09:42',
    }
    let snapshot = createSessionSnapshot({ progress: null }, [])
    mockApi.getSessionState.mockImplementation(async () => snapshot)

    renderHook(() => useWorkspaceController())

    await waitFor(() => {
      expect(useWorkspaceStore.getState().currentSessionId).toBe('session-1')
    })

    act(() => {
      capturedSocketConfig?.onEvent({
        type: 'activity_appended',
        session_id: 'session-1',
        event_id: 'event-5',
        sequence: 5,
        server_cursor: 'session-1:5',
        data: { items: [appended] },
      })
    })

    expect(useWorkspaceStore.getState().activityBySessionId['session-1'].at(-1)?.body).toBe(
      'Bridge emitted a new activity item.',
    )

    snapshot = createSessionSnapshot({ progress: null }, [appended])
    await act(async () => {
      capturedSocketConfig?.onEvent({
        type: 'snapshot_required',
        session_id: 'session-1',
        event_id: 'event-6',
        sequence: 6,
        server_cursor: 'session-1:6',
      })
      await Promise.resolve()
    })

    await waitFor(() => {
      const activity = useWorkspaceStore.getState().activityBySessionId['session-1']
      expect(activity).toHaveLength(1)
      expect(activity.at(-1)?.body).toBe('Bridge emitted a new activity item.')
      expect(activity.some((item) => item.body === 'idle / waiting_for_prompt')).toBe(false)
    })
  })
})
