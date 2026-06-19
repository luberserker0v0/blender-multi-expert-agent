import { memo, useEffect, useRef } from 'react'
import type { RunStatus, McpConnectionStatus, McpToolCallRecord } from '../../types'
import TopPanel from '../Shared/TopPanel'
import InspectorMetric from './InspectorMetric'

interface RuntimeLogPanelProps {
  open?: boolean
  runStatus: RunStatus
  mcpStatus: McpConnectionStatus
  consoleLog: string
  mcpToolCalls: McpToolCallRecord[]
  onClose: () => void
}

function RuntimeLogPanel({
  open = true,
  runStatus,
  mcpStatus,
  consoleLog,
  mcpToolCalls,
  onClose,
}: RuntimeLogPanelProps) {
  const preRef = useRef<HTMLPreElement>(null)
  const isAtBottomRef = useRef(true)

  useEffect(() => {
    const el = preRef.current
    if (!el) return
    if (isAtBottomRef.current) {
      el.scrollTop = el.scrollHeight
    }
  }, [consoleLog])

  const handleScroll = () => {
    const el = preRef.current
    if (!el) return
    const threshold = 40
    isAtBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < threshold
  }

  return (
    <TopPanel open={open} onClose={onClose} title="Runtime Console" subtitle="Runtime Log">
      <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
        <div className="space-y-3" data-testid="runtime-metrics">
          <InspectorMetric label="Workflow" value={runStatus.workflow_status} testId="runtime-metric-workflow" />
          <InspectorMetric label="Process" value={runStatus.process_status} testId="runtime-metric-process" />
          <InspectorMetric label="PID" value={runStatus.pid ? String(runStatus.pid) : 'N/A'} testId="runtime-metric-pid" />
          <InspectorMetric
            label="Exit Code"
            value={runStatus.exit_code !== null ? String(runStatus.exit_code) : 'N/A'}
            testId="runtime-metric-exit-code"
          />
          <InspectorMetric label="MCP State" value={mcpStatus.state} testId="runtime-metric-mcp-state" />
        </div>
        <div className="rounded-[28px] border border-white/8 bg-[#171614] p-5" data-testid="runtime-log-panel">
          <p className="text-xs uppercase tracking-[0.24em] text-stone-500">Runtime Console</p>
          <pre
            ref={preRef}
            onScroll={handleScroll}
            data-testid="runtime-console"
            className="mt-4 max-h-[420px] overflow-auto rounded-[24px] bg-black/30 px-4 py-4 text-xs leading-6 text-stone-200"
          >
            {consoleLog || 'No runtime stdout/stderr has been captured for this session yet.'}
          </pre>
          <div className="mt-5" data-testid="runtime-tool-calls">
            <p className="text-xs uppercase tracking-[0.24em] text-stone-500">MCP Tool Calls</p>
            {mcpToolCalls.length > 0 ? (
              <div className="mt-3 space-y-3" data-testid="runtime-tool-call-list">
                {mcpToolCalls.map((entry, index) => (
                  <div
                    key={`${entry.timestamp}-${entry.tool_name}-${index}`}
                    data-testid="runtime-tool-call-item"
                    className="rounded-2xl border border-white/8 bg-white/5 px-4 py-3"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-mono text-sm text-stone-100" data-testid="runtime-tool-call-name">
                        {entry.tool_name}
                      </span>
                      <span
                        data-testid="runtime-tool-call-status"
                        className={`rounded-full px-2 py-1 text-[10px] uppercase ${
                          entry.is_error
                            ? 'bg-rose-500/15 text-rose-300'
                            : 'bg-emerald-500/15 text-emerald-300'
                        }`}
                      >
                        {entry.is_error ? 'error' : 'ok'}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-stone-500" data-testid="runtime-tool-call-timestamp">
                      {entry.timestamp}
                    </p>
                    <pre
                      className="mt-3 overflow-x-auto rounded-2xl bg-black/30 px-3 py-3 text-[11px] leading-5 text-stone-200"
                      data-testid="runtime-tool-call-arguments"
                    >
                      {JSON.stringify(entry.arguments, null, 2)}
                    </pre>
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-3 text-sm text-stone-400">No executed Blender MCP tool calls have been recorded for this session yet.</p>
            )}
          </div>
        </div>
      </div>
    </TopPanel>
  )
}

export default memo(RuntimeLogPanel)
