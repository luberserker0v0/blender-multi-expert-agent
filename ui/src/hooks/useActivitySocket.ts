import { useEffect, useRef, useState } from 'react'
import type { ActivityEventEnvelope } from '../types'

type ActivitySocketState = 'connecting' | 'live' | 'reconnecting' | 'fallback'

const ACTIVITY_SOCKET_URL =
  import.meta.env.VITE_ACTIVITY_SOCKET_URL ?? 'ws://127.0.0.1:8766/ws/activity'
const RECONNECT_SCHEDULE_MS = [1000, 2000, 5000, 10000, 15000]
const FALLBACK_POLL_INTERVAL_MS = 5000

interface UseActivitySocketParams {
  currentSessionId: string
  onEvent?: (event: ActivityEventEnvelope) => void
  onActivitySnapshot?: (payload: Record<string, unknown>) => void
  onMeetingEvent?: (event: Record<string, unknown>) => void
  onPoll: (sessionId: string) => Promise<void>
}

function getReconnectDelay(attempt: number) {
  return RECONNECT_SCHEDULE_MS[Math.min(attempt, RECONNECT_SCHEDULE_MS.length - 1)]
}

function buildActivitySocketUrl(sessionId: string) {
  return `${ACTIVITY_SOCKET_URL}?session_id=${encodeURIComponent(sessionId)}`
}

export default function useActivitySocket({
  currentSessionId,
  onEvent,
  onActivitySnapshot,
  onMeetingEvent,
  onPoll,
}: UseActivitySocketParams): { activitySocketState: ActivitySocketState } {
  const [activitySocketState, setActivitySocketState] = useState<ActivitySocketState>(() =>
    currentSessionId ? 'connecting' : 'fallback',
  )
  const activitySocketRef = useRef<WebSocket | null>(null)

  // Store callbacks in refs so the effect doesn't depend on them directly.
  const onEventRef = useRef(onEvent)
  const onActivitySnapshotRef = useRef(onActivitySnapshot)
  const onMeetingEventRef = useRef(onMeetingEvent)
  const onPollRef = useRef(onPoll)

  useEffect(() => {
    onEventRef.current = onEvent
    onActivitySnapshotRef.current = onActivitySnapshot
    onMeetingEventRef.current = onMeetingEvent
    onPollRef.current = onPoll
  }, [onEvent, onActivitySnapshot, onMeetingEvent, onPoll])

  useEffect(() => {
    if (!currentSessionId) {
      activitySocketRef.current?.close()
      activitySocketRef.current = null
      const stateTimer = window.setTimeout(() => setActivitySocketState('fallback'), 0)
      return () => window.clearTimeout(stateTimer)
    }

    let disposed = false
    let reconnectTimer: number | null = null
    let fallbackTimer: number | null = null
    let reconnectAttempt = 0

    const stopFallbackPolling = () => {
      if (fallbackTimer !== null) {
        window.clearInterval(fallbackTimer)
        fallbackTimer = null
      }
    }

    const startFallbackPolling = () => {
      if (fallbackTimer !== null) return
      setActivitySocketState('fallback')
      fallbackTimer = window.setInterval(() => {
        void onPollRef.current(currentSessionId)
      }, FALLBACK_POLL_INTERVAL_MS)
    }

    const scheduleReconnect = () => {
      if (disposed) return
      const delay = getReconnectDelay(reconnectAttempt)
      reconnectAttempt += 1
      setActivitySocketState('reconnecting')
      startFallbackPolling()
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null
        connect()
      }, delay)
    }

    const connect = () => {
      if (disposed) return
      setActivitySocketState(reconnectAttempt === 0 ? 'connecting' : 'reconnecting')
      const socket = new WebSocket(buildActivitySocketUrl(currentSessionId))
      activitySocketRef.current = socket

      socket.onopen = () => {
        if (disposed) return
        reconnectAttempt = 0
        setActivitySocketState('live')
        stopFallbackPolling()
      }

      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(String(event.data)) as ActivityEventEnvelope
          if (onEventRef.current) {
            onEventRef.current(payload)
            return
          }
          if (payload.type === 'meeting_event') {
            onMeetingEventRef.current?.((payload.data ?? {}) as Record<string, unknown>)
            return
          }
          onActivitySnapshotRef.current?.(payload as unknown as Record<string, unknown>)
        } catch {
          // ignore malformed websocket payloads
        }
      }

      socket.onerror = () => {
        socket.close()
      }

      socket.onclose = () => {
        if (disposed) return
        if (activitySocketRef.current === socket) {
          activitySocketRef.current = null
        }
        scheduleReconnect()
      }
    }

    connect()

    return () => {
      disposed = true
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer)
      }
      stopFallbackPolling()
      if (activitySocketRef.current) {
        activitySocketRef.current.close()
      }
      activitySocketRef.current = null
    }
  }, [currentSessionId])

  return { activitySocketState }
}
