import { type ReactNode, memo } from 'react'

interface FullscreenOverlayProps {
  title: string
  onClose: () => void
  children: ReactNode
}

function FullscreenOverlay({
  title,
  onClose,
  children,
}: FullscreenOverlayProps) {
  return (
    <div className="fixed inset-0 z-40 bg-black/55 p-4 backdrop-blur-sm">
      <div className="mx-auto flex h-full max-w-[1500px] flex-col overflow-hidden rounded-[32px] border border-white/8 bg-[#1a1816] shadow-2xl shadow-black/40">
        <div className="flex items-start justify-between gap-3 border-b border-white/8 px-6 py-5">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-stone-500">Overlay</p>
            <h2 className="mt-2 text-2xl font-semibold text-stone-100">{title}</h2>
          </div>
          <button
            className="flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-lg text-stone-300 transition hover:bg-white/10 hover:text-white"
            onClick={onClose}
            type="button"
          >
            ×
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-6">
          {children}
        </div>
      </div>
    </div>
  )
}

export default memo(FullscreenOverlay)
