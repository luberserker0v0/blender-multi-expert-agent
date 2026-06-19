import { DEFAULT_MCP_STATUS, DEFAULT_RETRY_PROMPT, DEFAULT_RUN_STATUS, DEFAULT_WORKSPACE_DRAFT } from '../constants'
import { defaultSettings } from '../data/sampleSession'
import type {
  ActivityEventEnvelope,
  ActivityItem,
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

const MOCK_SESSION_ID = 'mcp-browser-session'
const MOCK_SERVER_NAME = 'blender'
type MockPatch = Partial<Omit<SessionStateSnapshot, 'workspace' | 'run_status' | 'retry_prompt' | 'mcp_status'>> & {
  workspace?: Partial<WorkspaceDraft>
  run_status?: Partial<RunStatus>
  retry_prompt?: Partial<RetryPromptState>
  mcp_status?: Partial<McpConnectionStatus>
}

interface MockState {
  settings: SavedSettings
  sessions: SessionSummary[]
  currentSessionId: string
  workspaces: Record<string, WorkspaceDraft>
  activity: Record<string, ActivityItem[]>
  progress: Record<string, MultiStageProgressSnapshot | null>
  runStatus: Record<string, RunStatus>
  retryPrompt: Record<string, RetryPromptState>
  consoleLog: Record<string, string>
  mcpToolCalls: Record<string, McpToolCallRecord[]>
  mcpStatus: McpConnectionStatus
  serverCursor: number
  sequence: number
  nextSessionIndex: number
}

interface McpBrowserMockApi {
  reset(): void
  getState(): MockState
  patchSession(sessionId: string, patch: MockPatch): void
  pushMeetingEvent(sessionId: string, event: Record<string, unknown>): void
  pushActivityItems(sessionId: string, items: ActivityItem[]): void
  setMcpStatus(status: Partial<McpConnectionStatus>): void
}

declare global {
  interface Window {
    __AI3D_MCP_MOCK__?: McpBrowserMockApi
  }
}

function isoNow() {
  return new Date().toISOString()
}

function createEmptyProgress(): MultiStageProgressSnapshot {
  return {
    workflow_type: 'multi_stage_modeling',
    status: 'idle',
    task: '',
    stage: 'idle',
    stage_status: 'waiting_for_prompt',
    active_task_id: '',
    completed_task_ids: [],
    part_tasks: [],
    assembly: {
      status: 'pending',
      current_round: 0,
      approved: false,
      all_parts_visible: false,
      initial_placement_applied: false,
      rounds: [],
    },
    final_validation: {
      status: 'pending',
      capture_path: '',
      viewpoint: 'front',
      detected_parts: [],
      missing_critical_parts: [],
      quantitative_metrics: [],
    },
    stop_reason: '',
  }
}

function createConnectedMcpStatus(): McpConnectionStatus {
  return {
    ...DEFAULT_MCP_STATUS,
    enabled: true,
    state: 'connected',
    message: 'Mock Blender MCP is connected.',
    server_name: MOCK_SERVER_NAME,
    tools: [
      {
        name: 'create_cube',
        description: 'Create a cube in the Blender scene.',
      },
      {
        name: 'move_object',
        description: 'Move an object to a target location.',
      },
    ],
  }
}

function createSessionSummary(sessionId: string, title: string): SessionSummary {
  return {
    id: sessionId,
    title,
    updatedAt: isoNow(),
  }
}

function createInitialState(): MockState {
  return {
    settings: {
      ...defaultSettings,
      useYoloValidation: false,
      yoloModelPath: '',
      yoloViewpoints: 'front',
    },
    sessions: [createSessionSummary(MOCK_SESSION_ID, 'MCP Browser Session')],
    currentSessionId: MOCK_SESSION_ID,
    workspaces: {
      [MOCK_SESSION_ID]: { ...DEFAULT_WORKSPACE_DRAFT },
    },
    activity: {
      [MOCK_SESSION_ID]: [],
    },
    progress: {
      [MOCK_SESSION_ID]: createEmptyProgress(),
    },
    runStatus: {
      [MOCK_SESSION_ID]: {
        ...DEFAULT_RUN_STATUS,
        session_id: MOCK_SESSION_ID,
      },
    },
    retryPrompt: {
      [MOCK_SESSION_ID]: {
        ...DEFAULT_RETRY_PROMPT,
        session_id: MOCK_SESSION_ID,
      },
    },
    consoleLog: {
      [MOCK_SESSION_ID]: '',
    },
    mcpToolCalls: {
      [MOCK_SESSION_ID]: [],
    },
    mcpStatus: createConnectedMcpStatus(),
    serverCursor: 0,
    sequence: 0,
    nextSessionIndex: 1,
  }
}

function cloneState(state: MockState): MockState {
  return JSON.parse(JSON.stringify(state)) as MockState
}

function deriveSessionTitle(workspace: WorkspaceDraft) {
  const fromTask = String(workspace.taskInput ?? '').trim()
  if (fromTask) return fromTask.slice(0, 60)
  const fromReference = String(workspace.referenceText ?? '').trim()
  if (fromReference) return fromReference.slice(0, 60)
  return 'New modeling session'
}

function createJsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json',
    },
  })
}

function sessionIdFromUrl(url: URL, state: MockState) {
  return url.searchParams.get('session_id') || state.currentSessionId || MOCK_SESSION_ID
}

function ensureSessionState(state: MockState, sessionId: string) {
  if (!state.workspaces[sessionId]) {
    state.workspaces[sessionId] = { ...DEFAULT_WORKSPACE_DRAFT }
  }
  if (!state.activity[sessionId]) {
    state.activity[sessionId] = []
  }
  if (!state.progress[sessionId]) {
    state.progress[sessionId] = createEmptyProgress()
  }
  if (!state.runStatus[sessionId]) {
    state.runStatus[sessionId] = { ...DEFAULT_RUN_STATUS, session_id: sessionId }
  }
  if (!state.retryPrompt[sessionId]) {
    state.retryPrompt[sessionId] = { ...DEFAULT_RETRY_PROMPT, session_id: sessionId }
  }
  if (!state.consoleLog[sessionId]) {
    state.consoleLog[sessionId] = ''
  }
  if (!state.mcpToolCalls[sessionId]) {
    state.mcpToolCalls[sessionId] = []
  }
}

function getSessionSnapshot(state: MockState, sessionId: string): SessionStateSnapshot {
  ensureSessionState(state, sessionId)
  return {
    session_id: sessionId,
    workspace: state.workspaces[sessionId],
    activity: state.activity[sessionId],
    progress: state.progress[sessionId],
    run_status: state.runStatus[sessionId],
    retry_prompt: state.retryPrompt[sessionId],
    console_log: state.consoleLog[sessionId],
    mcp_tool_calls: state.mcpToolCalls[sessionId],
    mcp_status: state.mcpStatus,
    server_cursor: `${sessionId}:${state.serverCursor}`,
    snapshot_generated_at: Date.now(),
  }
}

function nextEnvelopeMeta(state: MockState, sessionId: string) {
  state.sequence += 1
  state.serverCursor += 1
  return {
    event_id: `${sessionId}:event:${state.sequence}`,
    sequence: state.sequence,
    server_cursor: `${sessionId}:${state.serverCursor}`,
  }
}

type SocketMessageHandler = ((event: MessageEvent<string>) => void) | null
type SocketStateHandler = ((event: Event) => void) | null

class MockActivitySocket {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3

  readonly url: string
  readonly readyState = MockActivitySocket.OPEN
  readonly protocol = ''
  readonly extensions = ''
  readonly bufferedAmount = 0
  binaryType: BinaryType = 'blob'
  onopen: SocketStateHandler = null
  onmessage: SocketMessageHandler = null
  onerror: SocketStateHandler = null
  onclose: SocketStateHandler = null
  private closed = false
  readonly sessionId: string

  constructor(url: string) {
    this.url = url
    const parsed = new URL(url, window.location.origin)
    this.sessionId = parsed.searchParams.get('session_id') || MOCK_SESSION_ID
    mockSockets.add(this)
    window.setTimeout(() => {
      if (this.closed) return
      this.onopen?.(new Event('open'))
    }, 0)
  }

  close() {
    if (this.closed) return
    this.closed = true
    mockSockets.delete(this)
    this.onclose?.(new Event('close'))
  }

  send(_data: string | ArrayBufferLike | Blob | ArrayBufferView) {
    // UI does not send websocket messages in mock-first mode.
  }

  dispatchEnvelope(envelope: ActivityEventEnvelope) {
    if (this.closed) return
    this.onmessage?.(
      new MessageEvent('message', {
        data: JSON.stringify(envelope),
      }),
    )
  }
}

const mockSockets = new Set<MockActivitySocket>()

function emitEnvelope(sessionId: string, envelope: ActivityEventEnvelope) {
  for (const socket of mockSockets) {
    if (socket.sessionId === sessionId) {
      socket.dispatchEnvelope(envelope)
    }
  }
}

export function installMcpBrowserMocks() {
  if (window.__AI3D_MCP_MOCK__) return

  let state = createInitialState()
  const originalFetch = window.fetch.bind(window)
  const OriginalWebSocket = window.WebSocket

  const patchSession = (sessionId: string, patch: MockPatch) => {
    ensureSessionState(state, sessionId)
    if (patch.workspace) {
      state.workspaces[sessionId] = {
        ...state.workspaces[sessionId],
        ...patch.workspace,
      }
      const title = deriveSessionTitle(state.workspaces[sessionId])
      state.sessions = state.sessions.map((session) =>
        session.id === sessionId
          ? {
              ...session,
              title,
              updatedAt: isoNow(),
            }
          : session,
      )
    }
    if (patch.activity) {
      state.activity[sessionId] = [...patch.activity]
    }
    if (patch.progress !== undefined) {
      state.progress[sessionId] = patch.progress
    }
    if (patch.run_status) {
      state.runStatus[sessionId] = {
        ...state.runStatus[sessionId],
        ...patch.run_status,
        session_id: sessionId,
      }
    }
    if (patch.retry_prompt) {
      state.retryPrompt[sessionId] = {
        ...state.retryPrompt[sessionId],
        ...patch.retry_prompt,
        session_id: sessionId,
      }
    }
    if (typeof patch.console_log === 'string') {
      state.consoleLog[sessionId] = patch.console_log
    }
    if (patch.mcp_tool_calls) {
      state.mcpToolCalls[sessionId] = [...patch.mcp_tool_calls]
    }
    if (patch.mcp_status) {
      state.mcpStatus = {
        ...state.mcpStatus,
        ...patch.mcp_status,
      }
    }

    const meta = nextEnvelopeMeta(state, sessionId)
    emitEnvelope(sessionId, {
      type: 'snapshot_required',
      session_id: sessionId,
      ...meta,
    })
  }

  const pushMeetingEvent = (sessionId: string, event: Record<string, unknown>) => {
    ensureSessionState(state, sessionId)
    const meta = nextEnvelopeMeta(state, sessionId)
    emitEnvelope(sessionId, {
      type: 'meeting_event',
      session_id: sessionId,
      data: event,
      ...meta,
    })
  }

  const pushActivityItems = (sessionId: string, items: ActivityItem[]) => {
    ensureSessionState(state, sessionId)
    state.activity[sessionId] = [...state.activity[sessionId], ...items]
    const meta = nextEnvelopeMeta(state, sessionId)
    emitEnvelope(sessionId, {
      type: 'activity_appended',
      session_id: sessionId,
      data: { items },
      ...meta,
    })
  }

  const setMcpStatus = (status: Partial<McpConnectionStatus>) => {
    state.mcpStatus = {
      ...state.mcpStatus,
      ...status,
    }
  }

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const requestUrl =
      typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.toString()
          : input.url
    const url = new URL(requestUrl, window.location.origin)
    if (!url.pathname.startsWith('/api/')) {
      return originalFetch(input, init)
    }

    const method = (init?.method || (typeof input !== 'string' && !(input instanceof URL) ? input.method : 'GET')).toUpperCase()
    const bodyText =
      typeof init?.body === 'string'
        ? init.body
        : undefined
    const body = bodyText ? (JSON.parse(bodyText) as Record<string, unknown>) : {}

    if (url.pathname === '/api/bootstrap' && method === 'GET') {
      return createJsonResponse({
        sessions: state.sessions,
        current_session_id: state.currentSessionId,
        settings: {
          agent_orchestrator_base_url: state.settings.agentOrchestratorUrl,
          agent_orchestrator_model: state.settings.agentOrchestratorModel,
          agent_orchestrator_destroy_on_finish: !state.settings.keepAgentOrchestratorConversation,
          agent_orchestrator_timeout_seconds: state.settings.agentOrchestratorTimeoutSeconds,
          max_part_refinement_rounds: state.settings.maxPartRefinementRounds,
          max_assembly_rounds: state.settings.maxAssemblyRounds,
          use_yolo_perception: state.settings.useYoloValidation,
          yolo_model_path: state.settings.yoloModelPath,
          yolo_viewpoints: state.settings.yoloViewpoints
            .split(',')
            .map((item) => item.trim())
            .filter(Boolean),
        },
        mcp_status: state.mcpStatus,
      })
    }

    if (url.pathname === '/api/session/state' && method === 'GET') {
      const sessionId = sessionIdFromUrl(url, state)
      return createJsonResponse(getSessionSnapshot(state, sessionId))
    }

    if (url.pathname === '/api/activity/snapshot' && method === 'GET') {
      const sessionId = sessionIdFromUrl(url, state)
      return createJsonResponse(getSessionSnapshot(state, sessionId))
    }

    if (url.pathname === '/api/session/new' && method === 'POST') {
      const sessionId = `mcp-browser-session-${String(state.nextSessionIndex).padStart(3, '0')}`
      state.nextSessionIndex += 1
      ensureSessionState(state, sessionId)
      state.sessions = [createSessionSummary(sessionId, 'New modeling session'), ...state.sessions]
      return createJsonResponse({ session_id: sessionId })
    }

    if (url.pathname === '/api/session/delete' && method === 'POST') {
      const sessionId = String(body.session_id ?? '')
      state.sessions = state.sessions.filter((session) => session.id !== sessionId)
      delete state.workspaces[sessionId]
      delete state.activity[sessionId]
      delete state.progress[sessionId]
      delete state.runStatus[sessionId]
      delete state.retryPrompt[sessionId]
      delete state.consoleLog[sessionId]
      delete state.mcpToolCalls[sessionId]
      if (state.currentSessionId === sessionId) {
        state.currentSessionId = state.sessions[0]?.id ?? ''
      }
      return createJsonResponse({ deleted: true })
    }

    if (url.pathname === '/api/session/current' && method === 'POST') {
      const sessionId = String(body.session_id ?? '')
      state.currentSessionId = sessionId
      return createJsonResponse({ ok: true })
    }

    if (url.pathname === '/api/session/workspace' && method === 'POST') {
      const sessionId = String(body.session_id ?? state.currentSessionId)
      ensureSessionState(state, sessionId)
      state.workspaces[sessionId] = {
        taskInput: String(body.task_input ?? ''),
        referenceText: String(body.reference_text ?? ''),
        referenceImages: Array.isArray(body.reference_images) ? body.reference_images.map((item) => String(item)) : [],
      }
      const title = String(body.title ?? deriveSessionTitle(state.workspaces[sessionId]))
      state.sessions = state.sessions.map((session) =>
        session.id === sessionId
          ? {
              ...session,
              title,
              updatedAt: isoNow(),
            }
          : session,
      )
      return createJsonResponse({ workspace: state.workspaces[sessionId] })
    }

    if (url.pathname === '/api/activity/append' && method === 'POST') {
      const sessionId = String(body.session_id ?? state.currentSessionId)
      ensureSessionState(state, sessionId)
      const items = Array.isArray(body.activity) ? (body.activity as ActivityItem[]) : []
      state.activity[sessionId] = [...state.activity[sessionId], ...items]
      return createJsonResponse({ ok: true, count: items.length })
    }

    if (url.pathname === '/api/mcp/status' && method === 'GET') {
      return createJsonResponse(state.mcpStatus)
    }

    if (url.pathname === '/api/mcp/connect' && method === 'POST') {
      state.mcpStatus = createConnectedMcpStatus()
      return createJsonResponse(state.mcpStatus)
    }

    if (url.pathname === '/api/mcp/tool-calls' && method === 'GET') {
      const sessionId = sessionIdFromUrl(url, state)
      ensureSessionState(state, sessionId)
      return createJsonResponse({ tool_calls: state.mcpToolCalls[sessionId] })
    }

    if (url.pathname === '/api/run/status' && method === 'GET') {
      const sessionId = sessionIdFromUrl(url, state)
      ensureSessionState(state, sessionId)
      return createJsonResponse(state.runStatus[sessionId])
    }

    if (url.pathname === '/api/run/console' && method === 'GET') {
      const sessionId = sessionIdFromUrl(url, state)
      ensureSessionState(state, sessionId)
      return createJsonResponse({ content: state.consoleLog[sessionId] })
    }

    if (url.pathname === '/api/agent-orchestrator/live' && method === 'POST') {
      const endpoint = String(body.agent_orchestrator_base_url ?? '')
      return createJsonResponse({
        name: 'agent_orchestrator_health',
        ok: Boolean(endpoint),
        message: endpoint ? 'Agent Orchestrator is reachable.' : 'Provide an Agent Orchestrator URL before starting.',
      })
    }

    if (url.pathname === '/api/agent-orchestrator/models' && method === 'POST') {
      return createJsonResponse({
        ok: true,
        models: [
          { id: 'openai/gpt-5', provider: 'openai', model: 'gpt-5' },
          { id: 'anthropic/claude-3-5-sonnet', provider: 'anthropic', model: 'claude-3-5-sonnet' },
        ],
        message: 'Loaded 2 Agent Orchestrator models.',
      })
    }

    if (url.pathname === '/api/diagnostics/live' && method === 'POST') {
      return createJsonResponse({
        ok: state.mcpStatus.state === 'connected',
        checks: [
          {
            name: 'agent_orchestrator_health',
            ok: true,
            message: 'Agent Orchestrator is reachable.',
          },
          {
            name: 'agent_orchestrator_conversation_ready',
            ok: true,
            message: 'Agent Orchestrator conversation can be prepared.',
          },
          {
            name: 'blender_mcp',
            ok: state.mcpStatus.state === 'connected',
            message: state.mcpStatus.message,
          },
        ],
      })
    }

    if (url.pathname === '/api/settings' && method === 'POST') {
      state.settings = {
        agentOrchestratorUrl: String(body.agent_orchestrator_base_url ?? state.settings.agentOrchestratorUrl),
        agentOrchestratorModel: String(body.agent_orchestrator_model ?? state.settings.agentOrchestratorModel),
        keepAgentOrchestratorConversation: !Boolean(body.agent_orchestrator_destroy_on_finish ?? !state.settings.keepAgentOrchestratorConversation),
        agentOrchestratorTimeoutSeconds: Number(body.agent_orchestrator_timeout_seconds ?? state.settings.agentOrchestratorTimeoutSeconds),
        maxPartRefinementRounds: Number(body.max_part_refinement_rounds ?? state.settings.maxPartRefinementRounds),
        maxAssemblyRounds: Number(body.max_assembly_rounds ?? state.settings.maxAssemblyRounds),
        useYoloValidation: Boolean(body.use_yolo_perception ?? state.settings.useYoloValidation),
        yoloModelPath: String(body.yolo_model_path ?? state.settings.yoloModelPath),
        yoloViewpoints: Array.isArray(body.yolo_viewpoints)
          ? body.yolo_viewpoints.map((item) => String(item)).join(', ')
          : state.settings.yoloViewpoints,
      }
      return createJsonResponse({ ok: true })
    }

    if (url.pathname === '/api/run/start' && method === 'POST') {
      const sessionId = String(body.session_id ?? state.currentSessionId)
      ensureSessionState(state, sessionId)
      state.runStatus[sessionId] = {
        ...state.runStatus[sessionId],
        session_id: sessionId,
        workflow_status: 'running',
        process_status: 'running',
        error_message: '',
        last_command: ['mock-run'],
      }
      state.consoleLog[sessionId] = 'Mock run started.\n'
      state.progress[sessionId] = {
        ...createEmptyProgress(),
        task: String(body.task ?? state.workspaces[sessionId].taskInput),
        stage: 'design',
        stage_status: 'in_progress',
        status: 'running',
      }
      return createJsonResponse({
        started: true,
        session_id: sessionId,
        run_status: state.runStatus[sessionId],
      })
    }

    if (url.pathname === '/api/run/stop' && method === 'POST') {
      const sessionId = String(body.session_id ?? state.currentSessionId)
      ensureSessionState(state, sessionId)
      state.runStatus[sessionId] = {
        ...state.runStatus[sessionId],
        workflow_status: 'stopping',
        process_status: 'stopping',
      }
      state.consoleLog[sessionId] = `${state.consoleLog[sessionId]}Stop requested.\n`
      return createJsonResponse({
        stopped: true,
        run_status: state.runStatus[sessionId],
      })
    }

    if (url.pathname === '/api/run/retry' && method === 'POST') {
      const sessionId = String(body.session_id ?? state.currentSessionId)
      ensureSessionState(state, sessionId)
      state.retryPrompt[sessionId] = {
        ...DEFAULT_RETRY_PROMPT,
        session_id: sessionId,
      }
      state.runStatus[sessionId] = {
        ...state.runStatus[sessionId],
        workflow_status: 'running',
        process_status: 'running',
      }
      return createJsonResponse({
        started: true,
        session_id: sessionId,
        run_status: state.runStatus[sessionId],
      })
    }

    if (url.pathname === '/api/run/retry/stop' && method === 'POST') {
      const sessionId = String(body.session_id ?? state.currentSessionId)
      ensureSessionState(state, sessionId)
      state.retryPrompt[sessionId] = {
        ...DEFAULT_RETRY_PROMPT,
        session_id: sessionId,
      }
      return createJsonResponse({ ok: true })
    }

    return createJsonResponse({ error: `Unhandled mock endpoint: ${method} ${url.pathname}` }, 404)
  }

  ;(window as Window & typeof globalThis & { WebSocket: typeof WebSocket }).WebSocket =
    MockActivitySocket as unknown as typeof WebSocket

  window.__AI3D_MCP_MOCK__ = {
    reset() {
      state = createInitialState()
    },
    getState() {
      return cloneState(state)
    },
    patchSession,
    pushMeetingEvent,
    pushActivityItems,
    setMcpStatus,
  }

  console.info('[mcp-mock] Playwright MCP browser mocks installed')

  void OriginalWebSocket
}
