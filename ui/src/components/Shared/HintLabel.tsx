import { memo } from 'react'

interface HintLabelProps {
  label: string
  hint: string
  tooltipThreshold?: number
}

function HintLabel({ label, hint, tooltipThreshold = 72 }: HintLabelProps) {
  const useTooltip = hint.length > tooltipThreshold

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <label className="text-xs font-medium uppercase tracking-[0.18em] text-stone-400">{label}</label>
        {useTooltip ? (
          <span className="group relative inline-flex">
            <span
              aria-label={hint}
              className="flex h-5 w-5 cursor-help items-center justify-center rounded-full border border-white/10 bg-white/5 text-[11px] font-semibold normal-case tracking-normal text-stone-400 outline-none transition hover:bg-white/10 hover:text-stone-100 focus:border-amber-400/60 focus:bg-white/10 focus:text-stone-100"
              role="img"
              tabIndex={0}
            >
              i
            </span>
            <span className="pointer-events-none absolute left-1/2 top-7 z-50 hidden w-72 -translate-x-1/2 rounded-xl border border-white/10 bg-[#11100f] px-3 py-2 text-xs normal-case leading-5 tracking-normal text-stone-200 shadow-2xl shadow-black/40 group-hover:block group-focus-within:block">
              {hint}
            </span>
          </span>
        ) : null}
      </div>
      {!useTooltip ? <p className="text-xs leading-5 text-stone-500">{hint}</p> : null}
    </div>
  )
}

export default memo(HintLabel)
