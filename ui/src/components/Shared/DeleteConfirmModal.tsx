import { memo } from 'react'

interface DeleteConfirmModalProps {
  sessionTitle: string
  onCancel: () => void
  onConfirm: () => void
  eyebrow?: string
  description?: string
  confirmLabel?: string
}

function DeleteConfirmModal({
  sessionTitle,
  onCancel,
  onConfirm,
  eyebrow = 'Delete Session',
  description = 'This removes the local session progress file and keeps the current UI workspace focused on the remaining sessions.',
  confirmLabel = 'Delete',
}: DeleteConfirmModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-[28px] border border-white/70 bg-white/95 p-6 shadow-2xl shadow-slate-900/20">
        <p className="text-xs uppercase tracking-[0.24em] text-rose-500">{eyebrow}</p>
        <h3 className="mt-2 font-display text-2xl text-slate-950">{sessionTitle}</h3>
        <p className="mt-3 text-sm leading-6 text-slate-600">
          {description}
        </p>
        <div className="mt-6 flex justify-end gap-2">
          <button className="action-chip" onClick={onCancel} type="button">
            Cancel
          </button>
          <button className="rounded-full bg-rose-500 px-4 py-2 text-sm font-semibold text-white" onClick={onConfirm} type="button">
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

export default memo(DeleteConfirmModal)
