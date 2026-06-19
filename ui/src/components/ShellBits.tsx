import HintLabel from './Shared/HintLabel'

export function MetricCard({
  label,
  value,
  wide = false,
  testId,
}: {
  label: string
  value: string
  wide?: boolean
  testId?: string
}) {
  return (
    <article
      data-testid={testId}
      className={`rounded-[24px] bg-white/5 p-4 ring-1 ring-white/10 ${wide ? 'md:col-span-2 xl:col-span-2' : ''}`}
    >
      <p className="text-xs uppercase tracking-[0.2em] text-stone-400">{label}</p>
      <p className="mt-3 text-sm leading-6 text-stone-200" data-testid={testId ? `${testId}-value` : undefined}>
        {value}
      </p>
    </article>
  )
}

export function CaptureCard({ caption, path, testId }: { caption: string; path: string; testId?: string }) {
  return (
    <article className="rounded-[28px] bg-white/5 p-4 ring-1 ring-white/10" data-testid={testId}>
      <p className="text-xs uppercase tracking-[0.2em] text-stone-400">{caption}</p>
      <div className="mt-4 flex min-h-72 items-center justify-center rounded-[24px] border border-dashed border-stone-600 bg-gradient-to-br from-stone-800 to-stone-700 p-6 text-center">
        <div>
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-stone-700 text-sm font-semibold text-white">
            PNG
          </div>
          <p className="font-mono text-sm text-stone-400" data-testid={testId ? `${testId}-path` : undefined}>
            {path}
          </p>
        </div>
      </div>
    </article>
  )
}

export function SettingField({
  label,
  value,
  onChange,
  hint,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  hint?: string
}) {
  return (
    <label className="block">
      <span className="mb-2 block">
        {hint ? (
          <HintLabel hint={hint} label={label} />
        ) : (
          <span className="text-xs uppercase tracking-[0.22em] text-stone-400">{label}</span>
        )}
      </span>
      <input
        className="w-full rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-sm outline-none focus:border-cyan-400"
        onChange={(event) => onChange(event.target.value)}
        value={value}
      />
    </label>
  )
}

export function NumberField({
  label,
  value,
  onChange,
  hint,
}: {
  label: string
  value: number
  onChange: (value: number) => void
  hint?: string
}) {
  return (
    <label className="block">
      <span className="mb-2 block">
        {hint ? (
          <HintLabel hint={hint} label={label} />
        ) : (
          <span className="text-xs uppercase tracking-[0.22em] text-stone-400">{label}</span>
        )}
      </span>
      <input
        className="w-full rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-sm outline-none focus:border-cyan-400"
        min={1}
        onChange={(event) => onChange(Number(event.target.value))}
        type="number"
        value={value}
      />
    </label>
  )
}

export function ToggleField({
  label,
  checked,
  onChange,
  hint,
}: {
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
  hint?: string
}) {
  return (
    <button
      className="flex w-full items-center justify-between rounded-3xl border border-white/10 bg-white/5 px-4 py-3 text-left"
      onClick={() => onChange(!checked)}
      type="button"
    >
      <div>
        {hint ? <HintLabel hint={hint} label={label} /> : <p className="text-sm font-medium text-stone-200">{label}</p>}
        <p className="text-xs text-stone-400">{checked ? 'Enabled' : 'Disabled'}</p>
      </div>
      <span
        className={`flex h-7 w-12 items-center rounded-full p-1 transition ${
          checked ? 'bg-stone-700' : 'bg-stone-600'
        }`}
      >
        <span
          className={`h-5 w-5 rounded-full bg-white transition ${checked ? 'translate-x-5' : ''}`}
        />
      </span>
    </button>
  )
}
