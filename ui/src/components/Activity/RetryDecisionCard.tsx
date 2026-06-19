import type { RetryPromptState, RunStatus } from '../../types'
import { timeLabel } from '../../utils/formatters'
import React from 'react'

interface RetryDecisionCardProps {
  retryPrompt: RetryPromptState
  runStatus: RunStatus
  currentSessionId: string
  onRetry: (count: number) => void
  onStopRetry: () => void
}

function RetryDecisionCard({
  retryPrompt,
  runStatus,
  currentSessionId,
  onRetry,
  onStopRetry,
}: RetryDecisionCardProps) {
  const failureReason = String(retryPrompt.failure_reason ?? '').trim()
  return (
    <>
      {retryPrompt.show && retryPrompt.session_id === currentSessionId ? (
        <article
          className="max-w-3xl rounded-[24px] bg-rose-50 px-4 py-4 text-rose-950 ring-1 ring-rose-100 shadow-sm"
          data-testid="retry-card"
        >
          <div className="mb-2 flex items-center justify-between gap-3 text-xs uppercase tracking-[0.18em] opacity-70">
            <span>System</span>
            <span>{timeLabel()}</span>
          </div>
          <p className="text-sm leading-6" data-testid="retry-card-summary">
            The run is paused and waiting for your retry decision.
            {failureReason ? ` Reason: ${failureReason}` : ''}
          </p>
          <div
            className="mt-3 rounded-2xl bg-white/80 px-3 py-3 text-sm leading-6 text-rose-900 ring-1 ring-rose-100"
            data-testid="retry-card-counts"
          >
            <p data-testid="retry-card-current-attempt">
              Current attempt: {retryPrompt.attempt_index ?? runStatus.attempt_index ?? 0}
            </p>
            <p data-testid="retry-card-next-attempt">
              Next attempt if you retry:{' '}
              {retryPrompt.next_attempt_index ?? (runStatus.attempt_index ?? 0) + 1}
            </p>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              className="rounded-full bg-slate-900 px-4 py-2 text-sm font-medium text-white"
              data-testid="retry-card-action-retry-1"
              onClick={() => onRetry(1)}
              type="button"
            >
              Retry 1
            </button>
            <button
              className="rounded-full bg-white px-4 py-2 text-sm font-medium text-slate-700 ring-1 ring-slate-200"
              data-testid="retry-card-action-retry-3"
              onClick={() => onRetry(3)}
              type="button"
            >
              Retry 3
            </button>
            <button
              className="rounded-full bg-white px-4 py-2 text-sm font-medium text-rose-700 ring-1 ring-rose-200"
              data-testid="retry-card-action-stop"
              onClick={onStopRetry}
              type="button"
            >
              Stop retrying
            </button>
          </div>
        </article>
      ) : null}

      {retryPrompt.auto_retrying && retryPrompt.session_id === currentSessionId ? (
        <article
          className="max-w-3xl rounded-[24px] bg-amber-50 px-4 py-4 text-amber-950 ring-1 ring-amber-100 shadow-sm"
          data-testid="retry-auto-card"
        >
          <div className="mb-2 flex items-center justify-between gap-3 text-xs uppercase tracking-[0.18em] opacity-70">
            <span>Status</span>
            <span>{timeLabel()}</span>
          </div>
          <p className="text-sm leading-6" data-testid="retry-auto-summary">
            Auto retry is running. The agent is preparing attempt{' '}
            {retryPrompt.next_attempt_index ?? runStatus.attempt_index ?? 1}.
          </p>
          {(retryPrompt.remaining_retries ?? 0) > 0 ? (
            <p className="mt-2 text-sm leading-6 text-amber-800" data-testid="retry-auto-remaining">
              Remaining retry budget: {retryPrompt.remaining_retries}
            </p>
          ) : null}
        </article>
      ) : null}
    </>
  )
}

export default React.memo(RetryDecisionCard)
