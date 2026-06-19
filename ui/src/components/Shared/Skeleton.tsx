export function SkeletonLine({ className, width }: { className?: string; width?: string }) {
  return <div className={`h-4 rounded-full bg-white/10 animate-pulse ${className ?? ''}`} style={{ width }} />
}

export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div className={`animate-pulse rounded-2xl border border-white/8 bg-white/5 p-4 ${className ?? ''}`}>
      <SkeletonLine width="60%" />
      <SkeletonLine className="mt-3" width="40%" />
      <SkeletonLine className="mt-2" width="80%" />
    </div>
  )
}

export function SkeletonCircle({ size }: { size?: number }) {
  return (
    <div
      className="animate-pulse rounded-full bg-white/10"
      style={{ width: size ?? 32, height: size ?? 32 }}
    />
  )
}
