import { memo } from 'react'
import type { ActivityItem } from '../../types'
import {
  bubbleClass,
  getExpertRoleConfig,
} from '../../utils/formatters'
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';

interface ActivityBubbleProps {
  item: ActivityItem
  isExpanded: boolean
  onToggleExpand: (itemId: string) => void
}

function ActivityBubble({ item, isExpanded, onToggleExpand }: ActivityBubbleProps) {
  // ── Phase divider ──────────────────────────────────────────────
  if (item.kind === 'meeting_phase') {
    return (
      <div
        className={bubbleClass(item.kind)}
        data-testid="activity-item"
        data-activity-kind={item.kind}
        data-activity-id={item.id}
      >
        <div className="flex items-center gap-3">
          <div className="h-px flex-1 bg-white/10" />
          <span
            className="text-xs font-semibold uppercase tracking-[0.2em] text-stone-400"
            data-testid="activity-item-title"
          >
            {item.title}
          </span>
          <div className="h-px flex-1 bg-white/10" />
        </div>
        <span className="sr-only" data-testid="activity-item-kind">
          {item.kind}
        </span>
        {item.body && (
          <p className="mt-1 text-center text-[11px] text-stone-500" data-testid="activity-item-body">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeHighlight]}
              >
                {item.body}
              </ReactMarkdown>
          </p>
        )}
      </div>
    )
  }

  // ── Build/assemble step (compact) ──────────────────────────────
  if (item.kind === 'meeting_step') {
    return (
      <article
        className={bubbleClass(item.kind)}
        data-testid="activity-item"
        data-activity-kind={item.kind}
        data-activity-id={item.id}
        >
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-white" data-testid="activity-item-title">{item.title}</span>
            <span className="sr-only" data-testid="activity-item-kind">
              {item.kind}
            </span>
            <span className="shrink-0 text-[10px] text-white/75">{item.timestamp}</span>
          </div>
          {item.collapsible ? (
            <div className="space-y-2">
              <button
                className="flex items-center gap-2 text-left text-sm font-medium leading-6 text-white"
                data-testid="activity-item-toggle"
                onClick={() => onToggleExpand(item.id)}
                type="button"
              >
                <span className="text-xs">{isExpanded ? '\u25B2' : '\u25BC'}</span>
                <span className="flex-1" data-testid="activity-item-body">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    rehypePlugins={[rehypeHighlight]}
                  >
                    {item.body}
                  </ReactMarkdown>
                </span>
              </button>
              {isExpanded && item.responseBody ? (
                <div className="rounded-2xl bg-black/15 px-3 py-3" data-testid="activity-item-response">
                  <pre className="whitespace-pre-wrap text-xs leading-5 text-white/90">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      rehypePlugins={[rehypeHighlight]}
                    >
                      {item.responseBody}
                    </ReactMarkdown>
                  </pre>
                </div>
              ) : null}
            </div>
          ) : (
            <p className="text-sm leading-6 text-white" data-testid="activity-item-body">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeHighlight]}
              >
                {item.body}
              </ReactMarkdown>
            </p>
          )}
        </div>
      </article>
    )
  }

  // ── Expert spoke (llm kind with role tag) ──────────────────────
  const roleConfig = item.kind === 'llm' ? getExpertRoleConfig(item.title) : null
  const isDeliberationStep = item.kind === 'llm' && item.meetingFinal === false

  return (
    <article
      className={bubbleClass(item.kind)}
      data-testid="activity-item"
      data-activity-kind={item.kind}
      data-activity-id={item.id}
    >
      {/* Header */}
      <div className={`mb-2 flex items-center justify-between gap-3 text-xs uppercase tracking-[0.18em] ${isDeliberationStep ? 'opacity-55' : 'opacity-70'}`}>
        <div className="flex items-center gap-2">
          {roleConfig && <span>{roleConfig.icon}</span>}
          <span className={roleConfig?.color ?? ''} data-testid="activity-item-title">{item.title}</span>
          <span className="sr-only" data-testid="activity-item-kind">
            {item.kind}
          </span>
          {item.pairLabel ? (
            <span className="rounded-full bg-slate-900/8 px-2 py-1 text-[10px] font-semibold tracking-[0.14em] text-slate-600">
              {item.pairLabel}
            </span>
          ) : null}
          {item.llmDirection ? (
            <span
              className={`rounded-full px-2 py-1 text-[10px] font-semibold tracking-[0.14em] ${
                item.llmDirection === 'prompt'
                  ? 'bg-amber-100 text-amber-700'
                  : 'bg-cyan-100 text-cyan-700'
              }`}
            >
              {item.llmDirection === 'prompt' ? 'Prompt' : 'Response'}
            </span>
          ) : null}
        </div>
        <span>{item.timestamp}</span>
      </div>

      {/* Body: collapsible or direct */}
      {item.collapsible ? (
        <div className="space-y-3">
          <button
            className={`flex items-center gap-2 text-left text-sm font-medium leading-6 ${isDeliberationStep ? 'text-slate-700' : 'text-slate-900'}`}
            data-testid="activity-item-toggle"
            onClick={() => onToggleExpand(item.id)}
            type="button"
          >
            <span className="text-xs">{isExpanded ? '\u25B2' : '\u25BC'}</span>
            <span data-testid="activity-item-body">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeHighlight]}
              >
                {item.body}
              </ReactMarkdown>
            </span>
          </button>
          {isExpanded && item.responseBody ? (
            <div className={`rounded-2xl px-3 py-3 ${isDeliberationStep ? 'bg-black/3' : 'bg-black/5'}`} data-testid="activity-item-response">
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                {isDeliberationStep ? 'Deliberation Detail' : '\u5B8C\u6574 AO \u56DE\u8986'}
              </p>
              <pre className="whitespace-pre-wrap text-xs leading-5 text-slate-700">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  rehypePlugins={[rehypeHighlight]}
                >
                  {item.responseBody}
                </ReactMarkdown>
              </pre>
            </div>
          ) : null}
        </div>
      ) : (
        <p className={`text-sm leading-6 ${isDeliberationStep ? 'text-slate-600' : ''}`} data-testid="activity-item-body">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeHighlight]}
          >
            {item.body}
          </ReactMarkdown>
        </p>
      )}
    </article>
  )
}

export default memo(ActivityBubble)
