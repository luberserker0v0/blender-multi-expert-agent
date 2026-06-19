import React from 'react'
import type { SessionSummary } from '../../types'

interface SessionItemProps {
  session: SessionSummary
  isActive: boolean
  batchDeleteMode?: boolean
  selectedForBatchDelete?: boolean
  onSelect: (sessionId: string) => void
  onRequestDelete: (sessionId: string) => void
  onToggleBatchDeleteSelection?: (sessionId: string, selected: boolean) => void
}

const SessionItem: React.FC<SessionItemProps> = ({
  session,
  isActive,
  batchDeleteMode = false,
  selectedForBatchDelete = false,
  onSelect,
  onRequestDelete,
  onToggleBatchDeleteSelection,
}) => {
  return (
    <article
      className={`w-full rounded-2xl border px-4 py-3 text-left transition ${
        isActive
          ? 'border-amber-400/25 bg-amber-400/10 text-stone-100 shadow-lg shadow-black/10'
          : 'border-white/8 bg-white/5 text-stone-300 hover:border-white/16 hover:bg-white/8'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        {batchDeleteMode ? (
          <input
            aria-label={`Select ${session.title} for deletion`}
            checked={selectedForBatchDelete}
            className="mt-1 h-4 w-4 rounded border-white/20 bg-white/5 accent-rose-500"
            onChange={(event) => onToggleBatchDeleteSelection?.(session.id, event.target.checked)}
            type="checkbox"
          />
        ) : null}
        <button
          className="min-w-0 flex-1 text-left"
          onClick={() => {
            if (batchDeleteMode) {
              onToggleBatchDeleteSelection?.(session.id, !selectedForBatchDelete)
              return
            }
            onSelect(session.id)
          }}
          type="button"
        >
          <p className="line-clamp-2 text-sm font-semibold">{session.title}</p>
          <p className="mt-2 text-xs text-stone-500">{session.updatedAt}</p>
        </button>
        <div className="flex items-center gap-2">
          {session.unread ? <span className="h-2.5 w-2.5 rounded-full bg-amber-400" /> : null}
          {!batchDeleteMode ? (
            <button
              className="rounded-full border border-white/10 bg-white/5 px-2 py-1 text-[11px] font-medium text-stone-300 transition hover:bg-white/10 hover:text-white"
              onClick={(event) => {
                event.stopPropagation()
                onRequestDelete(session.id)
              }}
              type="button"
            >
              Delete
            </button>
          ) : null}
        </div>
      </div>
    </article>
  )
}

export default React.memo(SessionItem)
