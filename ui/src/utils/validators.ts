export function toPositiveNumber(value: unknown, fallback: number) {
  const next = Number(value)
  return Number.isFinite(next) && next > 0 ? next : fallback
}

export function toNonNegativeNumber(value: unknown, fallback: number) {
  const next = Number(value)
  return Number.isFinite(next) && next >= 0 ? next : fallback
}

export function toStringArray(value: unknown) {
  return Array.isArray(value) ? value.map((item) => String(item)) : []
}
