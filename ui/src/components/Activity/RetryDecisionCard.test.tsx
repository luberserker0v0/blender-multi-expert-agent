import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import RetryDecisionCard from './RetryDecisionCard'
import {
  mockRetryHidden,
  mockRetryShowing,
  mockRetryAutoRetrying,
  mockRunIdle,
  
} from '../../test/fixtures'

vi.mock('../../utils/formatters', () => ({
  timeLabel: () => '10:30',
}))

const SESSION_ID = 'gui-20260514-001'

function baseProps(overrides = {}) {
  return {
    retryPrompt: mockRetryHidden,
    runStatus: mockRunIdle,
    currentSessionId: SESSION_ID,
    onRetry: vi.fn(),
    onStopRetry: vi.fn(),
    ...overrides,
  }
}

describe('RetryDecisionCard', () => {
  it('renders nothing when show=false', () => {
    const { container } = render(<RetryDecisionCard {...baseProps()} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders nothing when session_id does not match currentSessionId', () => {
    const { container } = render(
      <RetryDecisionCard
        {...baseProps({
          retryPrompt: { ...mockRetryShowing, session_id: 'other-session' },
        })}
      />,
    )
    expect(container.innerHTML).toBe('')
  })

  it('renders retry decision card with three buttons when show=true', () => {
    render(<RetryDecisionCard {...baseProps({ retryPrompt: mockRetryShowing })} />)

    expect(screen.getByRole('button', { name: 'Retry 1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry 3' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Stop retrying' })).toBeInTheDocument()
  })

  it('displays failure reason text', () => {
    render(<RetryDecisionCard {...baseProps({ retryPrompt: mockRetryShowing })} />)

    expect(
      screen.getByText(/Part refinement failed after 3 rounds/),
    ).toBeInTheDocument()
  })

  it('displays current attempt and next attempt indices', () => {
    render(<RetryDecisionCard {...baseProps({ retryPrompt: mockRetryShowing })} />)

    expect(screen.getByText('Current attempt: 3')).toBeInTheDocument()
    expect(screen.getByText(/Next attempt if you retry:/)).toBeInTheDocument()
    expect(screen.getByText(/4/)).toBeInTheDocument()
  })

  it('fires onRetry with correct count when retry buttons are clicked', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    render(
      <RetryDecisionCard
        {...baseProps({ retryPrompt: mockRetryShowing, onRetry })}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Retry 1' }))
    expect(onRetry).toHaveBeenCalledWith(1)

    await user.click(screen.getByRole('button', { name: 'Retry 3' }))
    expect(onRetry).toHaveBeenCalledWith(3)
  })

  it('fires onStopRetry when Stop retrying button is clicked', async () => {
    const user = userEvent.setup()
    const onStopRetry = vi.fn()
    render(
      <RetryDecisionCard
        {...baseProps({ retryPrompt: mockRetryShowing, onStopRetry })}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Stop retrying' }))
    expect(onStopRetry).toHaveBeenCalledOnce()
  })

  it('renders auto-retrying card with attempt info', () => {
    render(
      <RetryDecisionCard
        {...baseProps({ retryPrompt: mockRetryAutoRetrying })}
      />,
    )

    expect(screen.getByText(/Auto retry is running/)).toBeInTheDocument()
    expect(screen.getByText(/preparing attempt 2/)).toBeInTheDocument()
  })

  it('shows remaining retry budget when remaining_retries > 0', () => {
    render(
      <RetryDecisionCard
        {...baseProps({ retryPrompt: mockRetryAutoRetrying })}
      />,
    )

    expect(screen.getByText(/Remaining retry budget: 1/)).toBeInTheDocument()
  })

  it('hides remaining retry budget when remaining_retries is 0', () => {
    const noRetriesLeft = { ...mockRetryAutoRetrying, remaining_retries: 0 }
    render(
      <RetryDecisionCard
        {...baseProps({ retryPrompt: noRetriesLeft })}
      />,
    )

    expect(screen.queryByText(/Remaining retry budget/)).not.toBeInTheDocument()
  })

  it('omits failure reason suffix when failure_reason is empty', () => {
    const noReason = { ...mockRetryShowing, failure_reason: '' }
    render(<RetryDecisionCard {...baseProps({ retryPrompt: noReason })} />)

    const body = screen.getByText(/The run is paused/)
    expect(body.textContent).not.toContain('Reason:')
  })
})
