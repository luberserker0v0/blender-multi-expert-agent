import { type ReactNode, memo } from 'react'

interface ToolbarButtonProps {
  active?: boolean
  label: string
  onClick: () => void
  children: ReactNode
}

function ToolbarButton({
  active = false,
  label,
  onClick,
  children,
  ...rest
}: ToolbarButtonProps & Record<string, unknown>) {
  return (
    <button
      aria-label={label}
      className={`flex h-11 w-11 items-center justify-center rounded-2xl border transition ${
        active
          ? 'border-amber-400/50 bg-amber-400/12 text-amber-200 shadow-lg shadow-amber-950/10'
          : 'border-white/8 bg-white/5 text-stone-300 hover:border-white/16 hover:bg-white/8 hover:text-white'
      }`}
      onClick={onClick}
      title={label}
      type="button"
      {...rest}
    >
      {children}
    </button>
  )
}

export default memo(ToolbarButton)
