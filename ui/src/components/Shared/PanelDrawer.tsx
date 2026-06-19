import { type ReactNode, memo } from 'react'

interface PanelDrawerProps {
  open: boolean
  onClose: () => void
  title: string
  subtitle?: string
  children: ReactNode
}

function PanelDrawer({ open, onClose, title, subtitle, children }: PanelDrawerProps) {
  return (
    <>
      {/* Backdrop */}
      <div
        className={`fixed inset-0 z-40 transition-opacity duration-300 ${
          open ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'
        }`}
        onClick={onClose}
      >
        <div className="absolute inset-0 bg-black/55 backdrop-blur-sm" />
      </div>

      {/* Drawer panel */}
      <div
        className={`fixed right-0 top-0 z-50 h-full transition-transform duration-300 ease-out ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <div className="flex h-full w-screen flex-col border-l border-white/8 bg-[#171614] shadow-2xl shadow-black/30 lg:max-w-[480px] lg:rounded-none">
          {/* Header */}
          <div className="flex items-start justify-between gap-3 border-b border-white/8 px-6 py-5">
            <div>
              {subtitle && (
                <p className="text-xs uppercase tracking-[0.24em] text-stone-500">{subtitle}</p>
              )}
              <h2 className={`font-semibold text-stone-100 ${subtitle ? 'mt-1 text-xl' : 'mt-0 text-2xl'}`}>
                {title}
              </h2>
            </div>
            <button
              className="flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-lg text-stone-300 transition hover:bg-white/10 hover:text-white"
              onClick={onClose}
              type="button"
            >
              ×
            </button>
          </div>

          {/* Content */}
          <div className="min-h-0 flex-1 overflow-y-auto p-6">
            {children}
          </div>
        </div>
      </div>
    </>
  )
}

export default memo(PanelDrawer)
