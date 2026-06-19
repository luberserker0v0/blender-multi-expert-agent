import { memo } from 'react'
import type { SessionSummary } from '../../types'
import SessionItem from './SessionItem'
import ToolbarButton from '../Shared/ToolbarButton'
import { SkeletonCard } from '../Shared/Skeleton'

interface SidebarProps {
  model: {
    sessions: SessionSummary[]
    currentSessionId: string
    settingsOpen: boolean
    sidebarOpen: boolean
    batchDeleteMode: boolean
    batchDeleteSelectedIds: string[]
  }
  actions: {
    onSelectSession: (sessionId: string) => void
    onRequestDeleteSession: (sessionId: string) => void
    onNewSession: () => void
    onToggleSettings: () => void
    onCloseSidebar: () => void
    onToggleBatchDeleteMode: () => void
    onToggleBatchDeleteSelection: (sessionId: string, selected: boolean) => void
    onRequestBatchDelete: () => void
  }
}

function Sidebar({
  model,
  actions,
}: SidebarProps) {
  return (
    <>
      {model.sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/55 lg:hidden"
          onClick={actions.onCloseSidebar}
        />
      )}

      <aside
        className={`
          w-[320px] shrink-0 overflow-hidden rounded-[28px] border border-white/8 bg-[#171614] p-4 shadow-2xl shadow-black/20
          ${model.sidebarOpen
            ? 'fixed left-0 top-0 z-30 flex h-full flex-col'
            : 'hidden'
          }
          lg:static lg:flex lg:h-auto lg:flex-col
        `}
      >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-xs font-semibold text-stone-100">
            A3D
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.22em] text-stone-500">Workspace</p>
            <h2 className="text-lg font-semibold text-stone-100">Sessions</h2>
          </div>
        </div>
        <ToolbarButton label="New Session" onClick={actions.onNewSession}>
          <svg aria-hidden="true" className="h-4 w-4" fill="none" viewBox="0 0 24 24">
            <path d="M12 5v14M5 12h14" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
          </svg>
        </ToolbarButton>
      </div>

      <div className="mt-4 flex items-center gap-2">
        <button
          className={`rounded-full border px-3 py-2 text-xs font-semibold transition ${
            model.batchDeleteMode
              ? 'border-rose-400/40 bg-rose-500/12 text-rose-200'
              : 'border-white/8 bg-white/5 text-stone-300 hover:bg-white/10 hover:text-white'
          }`}
          onClick={actions.onToggleBatchDeleteMode}
          type="button"
        >
          {model.batchDeleteMode ? 'Cancel Batch' : 'Batch Delete'}
        </button>
        {model.batchDeleteMode ? (
          <button
            className="rounded-full bg-rose-500 px-3 py-2 text-xs font-semibold text-white transition disabled:cursor-not-allowed disabled:bg-rose-500/35 disabled:text-white/60"
            disabled={model.batchDeleteSelectedIds.length === 0}
            onClick={actions.onRequestBatchDelete}
            type="button"
          >
            Delete
          </button>
        ) : null}
      </div>

      <div className="mt-5 min-h-0 flex-1 overflow-y-auto pr-1">
        <div className="space-y-2">
          {model.sessions.length > 0 ? (
            model.sessions.map((session) => (
              <SessionItem
                key={session.id}
                session={session}
                isActive={session.id === model.currentSessionId}
                batchDeleteMode={model.batchDeleteMode}
                selectedForBatchDelete={model.batchDeleteSelectedIds.includes(session.id)}
                onSelect={actions.onSelectSession}
                onRequestDelete={actions.onRequestDeleteSession}
                onToggleBatchDeleteSelection={actions.onToggleBatchDeleteSelection}
              />
            ))
          ) : (
            <div className="space-y-2">
              <SkeletonCard />
              <SkeletonCard />
              <SkeletonCard />
            </div>
          )}
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-white/8 pt-4">
        <ToolbarButton
          active={model.settingsOpen}
          label="Settings"
          onClick={actions.onToggleSettings}
        >
          <svg aria-hidden="true" className="h-4 w-4" fill="none" viewBox="0 0 24 24">
            <path
              d="M12 3.75l1.05 2.27 2.49.29 1.42 2.05-1.11 2.24 1.11 2.24-1.42 2.05-2.49.29L12 20.25l-1.05-2.27-2.49-.29-1.42-2.05 1.11-2.24-1.11-2.24 1.42-2.05 2.49-.29L12 3.75z"
              stroke="currentColor"
              strokeLinejoin="round"
              strokeWidth="1.5"
            />
            <circle cx="12" cy="12" r="3.25" stroke="currentColor" strokeWidth="1.5" />
          </svg>
        </ToolbarButton>
      </div>
    </aside>
    </>
  )
}

export default memo(Sidebar)
