import type { ActivityItem, RetryPromptState, RunStatus } from '../../types'
import { useActivityAutoScroll } from '../../hooks/useActivityAutoScroll'
import ActivityBubble from './ActivityBubble'
import RetryDecisionCard from './RetryDecisionCard'
import { SkeletonCard, SkeletonLine } from '../Shared/Skeleton'

interface ActivityFeedModel {
  activity: ActivityItem[]
  expandedActivityIds: string[]
  retryPrompt: RetryPromptState
  runStatus: RunStatus
  currentSessionId: string
  syncState: string
}

interface ActivityFeedActions {
  onToggleExpand: (itemId: string) => void
  onRetry: (count: number) => void
  onStopRetry: () => void
}

interface ActivityFeedProps {
  model: {
    activity: ActivityItem[]
    expandedActivityIds: string[]
    retryPrompt: RetryPromptState
    runStatus: RunStatus
    currentSessionId: string
    syncState: string
  }
  actions: {
    onToggleExpand: (itemId: string) => void
    onRetry: (count: number) => void
    onStopRetry: () => void
  }
}

type LegacyActivityFeedProps = {
  deferredActivity: ActivityItem[]
  expandedActivityIds: string[]
  onToggleExpand: (itemId: string) => void
  retryPrompt: RetryPromptState
  runStatus: RunStatus
  currentSessionId: string
  syncState?: string
  onRetry: (count: number) => void
  onStopRetry: () => void
  onScrollToLatest?: () => void
  onScroll?: (e: React.UIEvent<HTMLDivElement>) => void
  scrollRef?: React.RefObject<HTMLDivElement | null>
  endRef?: React.RefObject<HTMLDivElement | null>
}

function isModernProps(props: ActivityFeedProps | LegacyActivityFeedProps): props is ActivityFeedProps {
  return 'model' in props && 'actions' in props
}

function activityRenderSignature(item: ActivityItem) {
  return [
    item.kind,
    item.title,
    item.body,
    item.timestamp,
    item.pairKey ?? '',
    item.llmDirection ?? '',
    item.responseBody ?? '',
  ].join('::')
}

function dedupeActivityForRender(items: ActivityItem[]) {
  const seenIds = new Set<string>()
  const seenSignatures = new Set<string>()
  return items.filter((item) => {
    if (item.id) {
      if (seenIds.has(item.id)) {
        return false
      }
      seenIds.add(item.id)
    }
    const signature = activityRenderSignature(item)
    if (seenSignatures.has(signature)) {
      return false
    }
    seenSignatures.add(signature)
    return true
  })
}

function ActivityFeed(props: ActivityFeedProps | LegacyActivityFeedProps) {
  const model: ActivityFeedModel = isModernProps(props)
    ? props.model
    : {
        activity: props.deferredActivity,
        expandedActivityIds: props.expandedActivityIds,
        retryPrompt: props.retryPrompt,
        runStatus: props.runStatus,
        currentSessionId: props.currentSessionId,
        syncState: props.syncState ?? 'live',
      }
  const actions: ActivityFeedActions = isModernProps(props)
    ? props.actions
    : {
        onToggleExpand: props.onToggleExpand,
        onRetry: props.onRetry,
        onStopRetry: props.onStopRetry,
      }
  const renderedActivity = dedupeActivityForRender(model.activity)
  const { scrollRef, endRef, handleScroll, scrollToLatest } = useActivityAutoScroll({
    itemCount: renderedActivity.length,
    onScroll: !isModernProps(props) ? props.onScroll : undefined,
    onScrollToLatest: !isModernProps(props) ? props.onScrollToLatest : undefined,
  })

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-[28px] border border-white/8 bg-[#181715] p-4 shadow-xl shadow-black/10">
      <div className="mb-3 flex shrink-0 items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.22em] text-stone-500">Activity</p>
          <h2 className="text-xl font-semibold text-stone-100">Conversation Surface</h2>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-full border border-white/8 bg-white/6 px-3 py-1 text-xs text-stone-400">
            {renderedActivity.length} messages
          </span>
          <span className="rounded-full border border-white/8 bg-white/6 px-3 py-1 text-xs text-stone-400">
            sync: {model.syncState}
          </span>
          <button className="action-chip px-3 py-1.5 text-xs" onClick={scrollToLatest} type="button">
            Latest
          </button>
        </div>
      </div>

      <div
        className="min-h-0 flex-1 overflow-y-auto pr-1"
        data-testid="activity-feed-scroll"
        onScroll={handleScroll}
        ref={scrollRef}
      >
        <div className="space-y-4">
          {renderedActivity.length > 0 ? (
            renderedActivity.map((item) => (
              <ActivityBubble
                key={item.id || activityRenderSignature(item)}
                item={item}
                isExpanded={model.expandedActivityIds.includes(item.id)}
                onToggleExpand={actions.onToggleExpand}
              />
            ))
          ) : (
            <>
              <SkeletonCard />
              <SkeletonLine className="w-3/4" />
              <SkeletonCard />
              <SkeletonLine className="w-1/2" />
              <SkeletonLine className="w-5/6" />
            </>
          )}

          <RetryDecisionCard
            retryPrompt={model.retryPrompt}
            runStatus={model.runStatus}
            currentSessionId={model.currentSessionId}
            onRetry={actions.onRetry}
            onStopRetry={actions.onStopRetry}
          />
          <div ref={endRef} />
        </div>
      </div>
    </section>
  )
}

export default ActivityFeed
