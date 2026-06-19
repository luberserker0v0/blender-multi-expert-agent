import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { createRef } from 'react'
import ActivityFeed from './ActivityFeed'
import {
  mockUserActivities,
  mockSystemActivities,
  mockFeedbackActivities,
  
  mockRetryHidden,
  mockRetryShowing,
  mockRunIdle,
  mockRunRunning,
} from '../../test/fixtures'
import type { ActivityItem, RetryPromptState, RunStatus } from '../../types'

function renderFeed(overrides: {
  deferredActivity?: ActivityItem[]
  retryPrompt?: RetryPromptState
  runStatus?: RunStatus
  currentSessionId?: string
  onScrollToLatest?: () => void
  onToggleExpand?: (id: string) => void
  onRetry?: (count: number) => void
  onStopRetry?: () => void
} = {}) {
  const scrollRef = createRef<HTMLDivElement>()
  const endRef = createRef<HTMLDivElement>()
  const onScrollToLatest = overrides.onScrollToLatest ?? vi.fn()
  const onToggleExpand = overrides.onToggleExpand ?? vi.fn()
  const onRetry = overrides.onRetry ?? vi.fn()
  const onStopRetry = overrides.onStopRetry ?? vi.fn()

  const result = render(
    <ActivityFeed
      deferredActivity={overrides.deferredActivity ?? []}
      expandedActivityIds={[]}
      onToggleExpand={onToggleExpand}
      retryPrompt={overrides.retryPrompt ?? mockRetryHidden}
      runStatus={overrides.runStatus ?? mockRunIdle}
      currentSessionId={overrides.currentSessionId ?? 'gui-20260514-001'}
      syncState="live"
      onRetry={onRetry}
      onStopRetry={onStopRetry}
      onScrollToLatest={onScrollToLatest}
      onScroll={vi.fn()}
      scrollRef={scrollRef}
      endRef={endRef}
    />,
  )

  return { ...result, scrollRef, endRef, onScrollToLatest, onToggleExpand, onRetry, onStopRetry }
}

describe('ActivityFeed', () => {
  // ── Empty state ─────────────────────────────────────────────────────

  it('renders skeleton loading placeholders when activity list is empty', () => {
    const { container } = renderFeed({ deferredActivity: [] })
    // Skeleton components use animate-pulse class
    const pulseElements = container.querySelectorAll('.animate-pulse')
    expect(pulseElements.length).toBeGreaterThan(0)
    // No activity bubbles should be present
    expect(screen.queryByText('You')).not.toBeInTheDocument()
    expect(screen.queryByText('System')).not.toBeInTheDocument()
  })

  // ── Rendering multiple items ────────────────────────────────────────

  it('renders multiple ActivityItems when provided', () => {
    const items: ActivityItem[] = [
      mockUserActivities[0],
      mockSystemActivities[0],
      mockFeedbackActivities[0],
    ]
    renderFeed({ deferredActivity: items })

    expect(screen.getByText('You')).toBeInTheDocument()
    expect(screen.getByText('System')).toBeInTheDocument()
    expect(screen.getByText('Feedback')).toBeInTheDocument()
    expect(
      screen.getByText(
        'Build a wooden chair with a clean straight backrest, simple square seat, and light bevel feel.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('Session initialized.')).toBeInTheDocument()
  })

  it('displays the correct message count in the header', () => {
    const items: ActivityItem[] = [mockUserActivities[0], mockSystemActivities[0]]
    renderFeed({ deferredActivity: items })
    expect(screen.getByText('2 messages')).toBeInTheDocument()
  })

  it('displays the current sync state in the header', () => {
    render(
      <ActivityFeed
        deferredActivity={mockUserActivities}
        expandedActivityIds={[]}
        onToggleExpand={vi.fn()}
        retryPrompt={mockRetryHidden}
        runStatus={mockRunIdle}
        currentSessionId="gui-20260514-001"
        syncState="resyncing"
        onRetry={vi.fn()}
        onStopRetry={vi.fn()}
      />,
    )

    expect(screen.getByText('sync: resyncing')).toBeInTheDocument()
  })

  // ── Scroll-to-latest button ─────────────────────────────────────────

  it('calls onScrollToLatest when "Latest" button is clicked', () => {
    const { onScrollToLatest } = renderFeed({ deferredActivity: mockUserActivities })
    const latestButton = screen.getByText('Latest')
    fireEvent.click(latestButton)
    expect(onScrollToLatest).toHaveBeenCalledTimes(1)
  })

  // ── RetryDecisionCard visibility ────────────────────────────────────

  it('shows RetryDecisionCard when retryPrompt.show=true and session matches', () => {
    renderFeed({
      deferredActivity: mockUserActivities,
      retryPrompt: mockRetryShowing,
      runStatus: mockRunRunning,
      currentSessionId: 'gui-20260514-001',
    })

    expect(
      screen.getByText(/The run is paused and waiting for your retry decision/),
    ).toBeInTheDocument()
    expect(screen.getByText('Retry 1')).toBeInTheDocument()
    expect(screen.getByText('Retry 3')).toBeInTheDocument()
    expect(screen.getByText('Stop retrying')).toBeInTheDocument()
  })

  it('hides RetryDecisionCard when retryPrompt.show=false', () => {
    renderFeed({
      deferredActivity: mockUserActivities,
      retryPrompt: mockRetryHidden,
      runStatus: mockRunIdle,
      currentSessionId: 'gui-20260514-001',
    })

    expect(
      screen.queryByText(/The run is paused and waiting for your retry decision/),
    ).not.toBeInTheDocument()
    expect(screen.queryByText('Retry 1')).not.toBeInTheDocument()
    expect(screen.queryByText('Stop retrying')).not.toBeInTheDocument()
  })

  it('hides RetryDecisionCard when session_id does not match currentSessionId', () => {
    renderFeed({
      deferredActivity: mockUserActivities,
      retryPrompt: mockRetryShowing,
      runStatus: mockRunRunning,
      currentSessionId: 'different-session-id',
    })

    expect(
      screen.queryByText(/The run is paused and waiting for your retry decision/),
    ).not.toBeInTheDocument()
  })

  // ── Retry button callbacks ──────────────────────────────────────────

  it('calls onRetry with correct count when retry buttons are clicked', () => {
    const { onRetry } = renderFeed({
      deferredActivity: [],
      retryPrompt: mockRetryShowing,
      runStatus: mockRunRunning,
      currentSessionId: 'gui-20260514-001',
    })

    fireEvent.click(screen.getByText('Retry 1'))
    expect(onRetry).toHaveBeenCalledWith(1)

    fireEvent.click(screen.getByText('Retry 3'))
    expect(onRetry).toHaveBeenCalledWith(3)
  })

  it('calls onStopRetry when "Stop retrying" button is clicked', () => {
    const { onStopRetry } = renderFeed({
      deferredActivity: [],
      retryPrompt: mockRetryShowing,
      runStatus: mockRunRunning,
      currentSessionId: 'gui-20260514-001',
    })

    fireEvent.click(screen.getByText('Stop retrying'))
    expect(onStopRetry).toHaveBeenCalledTimes(1)
  })
})
