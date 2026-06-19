import { memo } from 'react'

interface InspectorMetricProps {
  label: string
  value: string
  testId?: string
}

function InspectorMetric({ label, value, testId }: InspectorMetricProps) {
  return (
    <div className="rounded-[18px] border border-white/8 bg-black/15 px-3 py-3" data-testid={testId}>
      <p className="text-[11px] uppercase tracking-[0.18em] text-stone-500">{label}</p>
      <p className="mt-2 text-sm leading-6 text-stone-100" data-testid={testId ? `${testId}-value` : undefined}>
        {value}
      </p>
    </div>
  )
}

export default memo(InspectorMetric)
