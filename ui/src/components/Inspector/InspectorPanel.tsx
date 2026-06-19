import { memo } from 'react'
import type { MultiStageProgressSnapshot } from '../../types'
import TopPanel from '../Shared/TopPanel'
import { SkeletonCard } from '../Shared/Skeleton'
import { MetricCard, CaptureCard } from '../ShellBits'

interface InspectorBlockItem {
  label: string
  value: string
}

export interface InspectorBlock {
  title: string
  items: InspectorBlockItem[]
}

interface InspectorPanelProps {
  open?: boolean
  progress: MultiStageProgressSnapshot
  selectedTitle: string
  latestCapturePath: string
  selectionKind: 'task' | 'part-round' | 'assembly-round' | 'none'
  inspectorBlocks: InspectorBlock[]
  onClose: () => void
}

function InspectorPanel({
  open = true,
  progress,
  selectedTitle,
  latestCapturePath,
  selectionKind,
  inspectorBlocks,
  onClose,
}: InspectorPanelProps) {
  return (
    <TopPanel open={open} onClose={onClose} title="Progress Inspector" subtitle="Inspector">
      {progress.status !== 'idle' ? (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-2" data-testid="inspector-metrics">
              <MetricCard label="Status" value={progress.status} testId="inspector-metric-status" />
              <MetricCard label="Stage" value={`${progress.stage} / ${progress.stage_status}`} testId="inspector-metric-stage" />
              <MetricCard label="Active Task" value={progress.active_task_id || 'None'} testId="inspector-metric-active-task" />
              <MetricCard
                label="Detected Parts"
                value={progress.final_validation.detected_parts.join(', ') || 'Pending'}
                testId="inspector-metric-detected-parts"
              />
              <MetricCard
                label="Completed Tasks"
                value={progress.completed_task_ids.join(', ') || 'None'}
                testId="inspector-metric-completed-tasks"
                wide
              />
              <MetricCard
                label="Stop Reason"
                value={progress.stop_reason || 'Run is still active.'}
                testId="inspector-metric-stop-reason"
                wide
              />
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <CaptureCard
                caption="Latest Capture"
                path={latestCapturePath}
                testId="inspector-capture-latest"
              />
              <CaptureCard
                caption="Final Validation Capture"
                path={progress.final_validation.capture_path || 'Pending final validation'}
                testId="inspector-capture-final-validation"
              />
            </div>
          </div>
          <div
            className="rounded-[28px] bg-slate-950 p-5 text-slate-100 shadow-2xl shadow-slate-900/20"
            data-testid="inspector-panel"
            data-selection-kind={selectionKind}
          >
            <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Inspector</p>
            <h3 className="mt-2 text-2xl font-semibold" data-testid="inspector-selected-task-title">
              {selectedTitle}
            </h3>
            <div className="mt-5 space-y-4" data-testid="inspector-block-list">
              {inspectorBlocks.length > 0 ? (
                inspectorBlocks.map((block, blockIndex) => (
                  <section
                    className="rounded-3xl border border-white/10 bg-white/5 p-4 backdrop-blur-sm"
                    key={block.title}
                    data-testid="inspector-block"
                    data-inspector-block-index={blockIndex}
                  >
                    <h4 className="mb-3 text-xs uppercase tracking-[0.24em] text-slate-400" data-testid="inspector-block-title">
                      {block.title}
                    </h4>
                    <div className="space-y-2">
                      {block.items.map((item, itemIndex) => (
                        <div
                          className="grid grid-cols-[130px_minmax(0,1fr)] gap-3 rounded-2xl bg-white/5 px-3 py-2"
                          key={`${block.title}-${item.label}`}
                          data-testid="inspector-block-item"
                          data-inspector-block-item-index={itemIndex}
                        >
                          <span className="font-mono text-xs text-slate-400" data-testid="inspector-block-item-label">{item.label}</span>
                          <span className="break-all font-mono text-xs text-slate-100" data-testid="inspector-block-item-value">
                            {String(item.value)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </section>
                ))
              ) : (
                <div className="rounded-3xl border border-white/10 bg-white/5 p-4 text-sm text-slate-400">
                  No inspector details are available yet.
                </div>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <SkeletonCard className="h-20" />
            <SkeletonCard className="h-20" />
            <SkeletonCard className="h-20" />
            <SkeletonCard className="h-20" />
            <SkeletonCard className="h-20" />
            <SkeletonCard className="h-20" />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <SkeletonCard className="h-32" />
            <SkeletonCard className="h-32" />
          </div>
        </div>
      )}
    </TopPanel>
  )
}

export default memo(InspectorPanel)
