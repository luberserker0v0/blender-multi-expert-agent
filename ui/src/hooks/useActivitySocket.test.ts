import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import useActivitySocket from './useActivitySocket'

// ---------------------------------------------------------------------------
// Mock WebSocket
// ---------------------------------------------------------------------------

class MockWebSocket {
  url: string
  onopen: (() => void) | null = null
  onmessage: ((event: { data: unknown }) => void) | null = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  close() {
    this.onclose?.()
  }

  static instances: MockWebSocket[] = []
  static reset() {
    MockWebSocket.instances = []
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const SESSION_ID = 'test-session-123'
const WS_URL = `ws://127.0.0.1:8766/ws/activity?session_id=${SESSION_ID}`

function createProps(overrides: Record<string, unknown> = {}) {
  return {
    currentSessionId: SESSION_ID,
    onActivitySnapshot: vi.fn(),
    onMeetingEvent: vi.fn(),
    onPoll: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useActivitySocket', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    MockWebSocket.reset()
    ;(globalThis as Record<string, unknown>).WebSocket = MockWebSocket
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  // 1. Connect
  it('connects to the correct WebSocket URL on mount', () => {
    renderHook(() => useActivitySocket(createProps()))

    expect(MockWebSocket.instances).toHaveLength(1)
    expect(MockWebSocket.instances[0].url).toBe(WS_URL)
  })

  // 2. Initial state
  it('starts in connecting state', () => {
    const { result } = renderHook(() => useActivitySocket(createProps()))

    expect(result.current.activitySocketState).toBe('connecting')
  })

  // 3. Open → live + onPoll
  it('transitions to live without calling onPoll when WebSocket opens', () => {
    const props = createProps()
    const { result } = renderHook(() => useActivitySocket(props))

    act(() => {
      MockWebSocket.instances[0].onopen?.()
    })

    expect(result.current.activitySocketState).toBe('live')
    expect(props.onPoll).not.toHaveBeenCalled()
  })

  // 4. Parse JSON message → onActivitySnapshot
  it('parses incoming JSON and calls onActivitySnapshot with parsed payload', () => {
    const props = createProps()
    renderHook(() => useActivitySocket(props))

    const payload = {
      run_status: { workflow_status: 'running' },
      progress: { task: 'build a chair' },
    }

    act(() => {
      MockWebSocket.instances[0].onmessage?.({ data: JSON.stringify(payload) })
    })

    expect(props.onActivitySnapshot).toHaveBeenCalledOnce()
    expect(props.onActivitySnapshot).toHaveBeenCalledWith(payload)
  })

  // 5. Malformed message
  it('handles malformed WebSocket messages gracefully', () => {
    const props = createProps()
    const { result } = renderHook(() => useActivitySocket(props))

    expect(() => {
      act(() => {
        MockWebSocket.instances[0].onmessage?.({ data: 'not-json {{{' })
      })
    }).not.toThrow()

    expect(props.onActivitySnapshot).not.toHaveBeenCalled()
    expect(result.current.activitySocketState).toBe('connecting')
  })

  // 6. Reconnect backoff: 1s, 2s, 5s, 10s, 15s, then stays at 15s
  it('reconnects with escalating backoff on repeated disconnects', () => {
    renderHook(() => useActivitySocket(createProps()))
    const delays = [1000, 2000, 5000, 10_000, 15_000, 15_000]

    for (let i = 0; i < delays.length; i++) {
      const countBefore = MockWebSocket.instances.length
      act(() => {
        MockWebSocket.instances[countBefore - 1].onclose?.()
      })
      // Not yet
      act(() => { vi.advanceTimersByTime(delays[i] - 1) })
      expect(MockWebSocket.instances).toHaveLength(countBefore)
      // Now
      act(() => { vi.advanceTimersByTime(1) })
      expect(MockWebSocket.instances).toHaveLength(countBefore + 1)
    }
  })

  // 7. Fallback polling
  it('falls back to HTTP polling at 5s intervals after disconnect', () => {
    const props = createProps()
    renderHook(() => useActivitySocket(props))

    act(() => {
      MockWebSocket.instances[0].onclose?.()
    })

    // First poll at 5s
    act(() => { vi.advanceTimersByTime(5000) })
    expect(props.onPoll).toHaveBeenCalledWith(SESSION_ID)

    // Second poll at 10s
    act(() => { vi.advanceTimersByTime(5000) })
    expect(props.onPoll).toHaveBeenCalledTimes(2)
  })

  it('closes the previous socket and reconnects with a new session id on rerender', () => {
    const { rerender } = renderHook((props) => useActivitySocket(props), {
      initialProps: createProps(),
    })
    const closeSpy = vi.spyOn(MockWebSocket.instances[0], 'close')

    rerender({
      ...createProps(),
      currentSessionId: 'next-session-456',
    })

    expect(closeSpy).toHaveBeenCalled()
    expect(MockWebSocket.instances).toHaveLength(2)
    expect(MockWebSocket.instances[1].url).toBe(
      'ws://127.0.0.1:8766/ws/activity?session_id=next-session-456',
    )
  })

  it('remains stable across a StrictMode-style unmount/remount cycle and reconnects with a fresh socket', () => {
    const firstRender = renderHook(() => useActivitySocket(createProps()))
    const firstSocket = MockWebSocket.instances[0]
    const closeSpy = vi.spyOn(firstSocket, 'close')

    firstRender.unmount()
    renderHook(() => useActivitySocket(createProps()))

    expect(closeSpy).toHaveBeenCalled()
    expect(MockWebSocket.instances).toHaveLength(2)
    expect(MockWebSocket.instances[1].url).toBe(WS_URL)
  })

  // 8. Full state transition cycle
  it('transitions through connecting → live → fallback → reconnecting → live', () => {
    const props = createProps()
    const { result } = renderHook(() => useActivitySocket(props))

    // connecting
    expect(result.current.activitySocketState).toBe('connecting')

    // → live
    act(() => { MockWebSocket.instances[0].onopen?.() })
    expect(result.current.activitySocketState).toBe('live')

    // → fallback (reconnecting + fallback polling batched)
    act(() => { MockWebSocket.instances[0].onclose?.() })
    expect(result.current.activitySocketState).toBe('fallback')

    // → reconnecting (timer fires, connect() called with attempt > 0)
    act(() => { vi.advanceTimersByTime(1000) })
    expect(result.current.activitySocketState).toBe('reconnecting')

    // → live again
    act(() => { MockWebSocket.instances[1].onopen?.() })
    expect(result.current.activitySocketState).toBe('live')
  })

  // 9. Empty sessionId → immediate fallback
  it('falls back immediately when sessionId is empty', () => {
    const props = createProps({ currentSessionId: '' })
    const { result } = renderHook(() => useActivitySocket(props))

    expect(result.current.activitySocketState).toBe('fallback')
    expect(MockWebSocket.instances).toHaveLength(0)
  })

  // 10. Cleanup on unmount
  it('closes WebSocket and clears timers on unmount', () => {
    const { unmount } = renderHook(() => useActivitySocket(createProps()))
    const socket = MockWebSocket.instances[0]
    const closeSpy = vi.spyOn(socket, 'close')

    unmount()

    expect(closeSpy).toHaveBeenCalled()
  })

  // 11. Reconnect counter resets after successful connection
  it('resets reconnect backoff after a successful reconnection', () => {
    renderHook(() => useActivitySocket(createProps()))

    // Attempt 1: disconnect → wait 1s → reconnect
    act(() => { MockWebSocket.instances[0].onclose?.() })
    act(() => { vi.advanceTimersByTime(1000) })
    expect(MockWebSocket.instances).toHaveLength(2)

    // Attempt 2: disconnect → wait 2s → reconnect
    act(() => { MockWebSocket.instances[1].onclose?.() })
    act(() => { vi.advanceTimersByTime(2000) })
    expect(MockWebSocket.instances).toHaveLength(3)

    // Successful open resets the counter
    act(() => { MockWebSocket.instances[2].onopen?.() })

    // Disconnect again — should use 1s delay (counter reset)
    act(() => { MockWebSocket.instances[2].onclose?.() })
    act(() => { vi.advanceTimersByTime(999) })
    expect(MockWebSocket.instances).toHaveLength(3) // not yet
    act(() => { vi.advanceTimersByTime(1) })
    expect(MockWebSocket.instances).toHaveLength(4) // reconnected at 1s
  })
})
