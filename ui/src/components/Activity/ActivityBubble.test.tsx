import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import ActivityBubble from './ActivityBubble'
import type { ActivityItem } from '../../types'
import {
  mockUserActivities,
  mockSystemActivities,
  mockStatusActivities,
  mockFeedbackActivities,
  mockLlmActivities,
} from '../../test/fixtures'

const noop = vi.fn()

function renderItem(item: ActivityItem, isExpanded = false) {
  return render(
    <ActivityBubble item={item} isExpanded={isExpanded} onToggleExpand={noop} />,
  )
}

describe('ActivityBubble', () => {
  // ── Rendering per kind ──────────────────────────────────────────────

  it('renders user kind with title and body', () => {
    renderItem(mockUserActivities[0])
    expect(screen.getByText('You')).toBeInTheDocument()
    expect(
      screen.getByText(
        'Build a wooden chair with a clean straight backrest, simple square seat, and light bevel feel.',
      ),
    ).toBeInTheDocument()
  })

  it('renders system kind with title and body', () => {
    renderItem(mockSystemActivities[0])
    expect(screen.getByText('System')).toBeInTheDocument()
    expect(screen.getByText('Session initialized.')).toBeInTheDocument()
  })

  it('renders status kind with title and body', () => {
    renderItem(mockStatusActivities[0])
    expect(screen.getByText('Status')).toBeInTheDocument()
    expect(screen.getByText('planning / completed')).toBeInTheDocument()
  })

  it('renders feedback kind with title and body', () => {
    renderItem(mockFeedbackActivities[0])
    expect(screen.getByText('Feedback')).toBeInTheDocument()
    expect(
      screen.getByText(
        'Backrest is too short. Stretch the object upward before moving to the seat.',
      ),
    ).toBeInTheDocument()
  })

  it('renders agent turn kind (non-collapsible) with body text directly', () => {
    // mockLlmActivities[2] has collapsible: false
    renderItem(mockLlmActivities[2])
    expect(screen.getByText('Agent')).toBeInTheDocument()
    expect(
      screen.getByText('Assembly review completed - no issues found.'),
    ).toBeInTheDocument()
  })

  // ── Timestamp rendering ─────────────────────────────────────────────

  it('renders the timestamp', () => {
    renderItem(mockUserActivities[0])
    expect(screen.getByText('09:41')).toBeInTheDocument()
  })

  // ── CSS classes per kind ────────────────────────────────────────────

  it('applies user-specific CSS classes (bg-slate-900, text-white)', () => {
    const { container } = renderItem(mockUserActivities[0])
    const article = container.querySelector('article')!
    expect(article.className).toContain('bg-slate-900')
    expect(article.className).toContain('text-white')
    expect(article.className).toContain('ml-auto')
  })

  it('applies feedback-specific CSS classes (bg-cyan-50, text-cyan-950)', () => {
    const { container } = renderItem(mockFeedbackActivities[0])
    const article = container.querySelector('article')!
    expect(article.className).toContain('bg-cyan-50')
    expect(article.className).toContain('text-cyan-950')
  })

  it('applies status-specific CSS classes (bg-amber-50, text-amber-950)', () => {
    const { container } = renderItem(mockStatusActivities[0])
    const article = container.querySelector('article')!
    expect(article.className).toContain('bg-amber-50')
    expect(article.className).toContain('text-amber-950')
  })

  it('applies default CSS classes for system kind (bg-white/85, text-slate-800)', () => {
    const { container } = renderItem(mockSystemActivities[0])
    const article = container.querySelector('article')!
    expect(article.className).toContain('bg-white/85')
    expect(article.className).toContain('text-slate-800')
  })

  // ── Collapsible behavior for agent turn wire kind ───────────────────

  it('renders collapsible agent turn bubble with expand button when collapsed', () => {
    // mockLlmActivities[0] has collapsible: true, body: 'Task decomposition requested.'
    renderItem(mockLlmActivities[0], false)
    const toggleButton = screen.getByRole('button')
    expect(toggleButton).toBeInTheDocument()
    expect(screen.getByText('\u25BC')).toBeInTheDocument()
    // Header extracted from body
    expect(screen.getByText('Task decomposition requested.')).toBeInTheDocument()
  })

  it('expands collapsible llm bubble on click and shows body content', () => {
    const onToggle = vi.fn()
    render(
      <ActivityBubble
        item={mockLlmActivities[0]}
        isExpanded={false}
        onToggleExpand={onToggle}
      />,
    )

    // Click the toggle button
    fireEvent.click(screen.getByRole('button'))
    expect(onToggle).toHaveBeenCalledWith('la-1')
  })

  it('shows expanded content with collapse icon when isExpanded=true', () => {
    // When expanded, the icon should be ▲ and body content visible
    renderItem(mockLlmActivities[0], true)
    expect(screen.getByText('\u25B2')).toBeInTheDocument()
    // "Prompt" appears as the llmDirection badge
    const promptElements = screen.getAllByText('Prompt')
    expect(promptElements.length).toBe(1)
    // Body text in button header
    expect(screen.getByText('Task decomposition requested.')).toBeInTheDocument()
    // responseBody in expanded panel
    expect(screen.getByText('Decompose the task into sub-tasks: chair_back, chair_seat.')).toBeInTheDocument()
  })

  // ── Agent turn badges ───────────────────────────────────────────────

  it('renders pairLabel badge for agent turn items', () => {
    // mockLlmActivities[0] has pairLabel: 'Show response'
    renderItem(mockLlmActivities[0])
    expect(screen.getByText('Show response')).toBeInTheDocument()
  })

  it('renders turn direction badge as "Prompt" for prompt direction', () => {
    // mockLlmActivities[0] has llmDirection: 'prompt'
    renderItem(mockLlmActivities[0])
    expect(screen.getByText('Prompt')).toBeInTheDocument()
  })

  it('renders turn direction badge as "Response" for response direction', () => {
    // mockLlmActivities[1] has llmDirection: 'response'
    renderItem(mockLlmActivities[1])
    expect(screen.getByText('Response')).toBeInTheDocument()
  })
})
