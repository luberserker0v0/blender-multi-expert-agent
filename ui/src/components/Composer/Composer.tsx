import { memo } from 'react'
import type { SessionSummary } from '../../types'
import HintLabel from '../Shared/HintLabel'
import { SkeletonCard } from '../Shared/Skeleton'

interface ComposerModel {
  currentSession: SessionSummary | null
  currentSessionId: string
  taskInput: string
  referenceText: string
  referenceImages: string[]
  canStartRun: boolean
  canStopRun: boolean
  startBlockedReason: string
  liveDiagnosticsRunning: boolean
  settingsOpen: boolean
  progressStage: string
  workflowStatus: string
  activityState: string
  syncState: string
  agentOrchestratorReady: boolean
  mcpState: string
  composerExpanded: boolean
}

interface ComposerActions {
  onToggleComposer: () => void
  onTaskInputChange: (value: string) => void
  onReferenceTextChange: (value: string) => void
  onReferenceImagePick: (e: React.ChangeEvent<HTMLInputElement>) => void
  onStartRun: () => void
  onStopRun: () => void
  onRunLiveDiagnostics: () => void
  onToggleSettings: () => void
  onToggleInspector: () => void
  onToggleRuntime: () => void
}

interface ComposerProps {
  model: {
    currentSession: SessionSummary | null
    currentSessionId: string
    taskInput: string
    referenceText: string
    referenceImages: string[]
    canStartRun: boolean
    canStopRun: boolean
    startBlockedReason: string
    liveDiagnosticsRunning: boolean
    settingsOpen: boolean
    progressStage: string
    workflowStatus: string
    activityState: string
    syncState: string
    agentOrchestratorReady: boolean
    mcpState: string
    composerExpanded: boolean
  }
  actions: ComposerActions
}

type LegacyComposerProps = ComposerModel & ComposerActions

function isModernProps(props: ComposerProps | LegacyComposerProps): props is ComposerProps {
  return 'model' in props && 'actions' in props
}

function Composer(props: ComposerProps | LegacyComposerProps) {
  const model = isModernProps(props) ? props.model : props
  const actions = isModernProps(props) ? props.actions : props
  const canOperateOnSession = Boolean(model.currentSessionId && model.currentSession)

  return (
    <section className="shrink-0 rounded-[28px] border border-white/8 bg-[#181715]/95 p-5 shadow-2xl shadow-black/15 backdrop-blur">
      <div className="flex flex-col gap-5">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-[0.24em] text-stone-500">Current Session</p>
            <h1 className="mt-2 truncate text-2xl font-semibold tracking-tight text-stone-100">
              {model.currentSession?.title || 'Blender Modeling Operator'}
            </h1>
            <p className="mt-2 text-sm text-stone-400">
              {canOperateOnSession ? `Session ${model.currentSessionId}` : 'Create or open a session to begin'}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-white/8 bg-white/6 px-3 py-1 text-xs text-stone-300">
              stage: {model.progressStage || 'idle'}
            </span>
            <span className="rounded-full border border-white/8 bg-white/6 px-3 py-1 text-xs text-stone-300">
              workflow: {model.workflowStatus}
            </span>
            <span className="rounded-full border border-white/8 bg-white/6 px-3 py-1 text-xs text-stone-300">
              activity: {model.activityState}
            </span>
            <span className="rounded-full border border-white/8 bg-white/6 px-3 py-1 text-xs text-stone-300">
              sync: {model.syncState}
            </span>
            <span className="rounded-full border border-white/8 bg-white/6 px-3 py-1 text-xs text-stone-300">
              AO: {model.agentOrchestratorReady ? 'ready' : 'not verified'}
            </span>
            <span className="rounded-full border border-white/8 bg-white/6 px-3 py-1 text-xs text-stone-300">
              MCP: {model.mcpState}
            </span>
            <button
              className="action-chip"
              onClick={actions.onToggleComposer}
              type="button"
              title={model.composerExpanded ? 'Collapse input fields' : 'Expand input fields'}
            >
              {model.composerExpanded ? '▲ Collapse' : '▼ Expand Input'}
            </button>
            <button className="action-chip" onClick={actions.onToggleSettings} type="button">
              {model.settingsOpen ? 'Close Settings' : 'Settings'}
            </button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            className="action-chip disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!model.canStartRun}
            onClick={actions.onStartRun}
            type="button"
          >
            Start
          </button>
          <button
            className="action-chip disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!model.canStopRun}
            onClick={actions.onStopRun}
            type="button"
          >
            Stop
          </button>
          <button
            className="action-chip disabled:cursor-not-allowed disabled:opacity-50"
            disabled={model.liveDiagnosticsRunning}
            onClick={actions.onRunLiveDiagnostics}
            type="button"
          >
            {model.liveDiagnosticsRunning ? 'Verifying...' : 'Live Diagnostics'}
          </button>
          <button className="action-chip" onClick={actions.onToggleInspector} type="button">
            Inspector
          </button>
          <button className="action-chip" onClick={actions.onToggleRuntime} type="button">
            Runtime Log
          </button>
        </div>

        {model.composerExpanded ? (
          <>
            {model.startBlockedReason ? (
              <p className="rounded-2xl border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
                {model.startBlockedReason}
              </p>
            ) : null}

            {model.currentSession || model.taskInput ? (
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)_300px]">
                <div className="min-w-0 rounded-[24px] border border-white/8 bg-white/5 p-4">
                  <HintLabel
                    hint="Describe the main object the agent should deliver. This becomes the core modeling goal used for planning."
                    label="Task Prompt"
                  />
                  <textarea
                    className="mt-3 h-28 w-full rounded-3xl border border-white/10 bg-black/15 px-4 py-3 text-sm text-stone-100 outline-none transition placeholder:text-stone-500 focus:border-amber-400/50 focus:ring-4 focus:ring-amber-500/10"
                    onChange={(event) => actions.onTaskInputChange(event.target.value)}
                    placeholder="Example: Build a wooden chair with a straight backrest and square seat."
                    value={model.taskInput}
                  />
                </div>

                <div className="min-w-0 rounded-[24px] border border-white/8 bg-white/5 p-4">
                  <HintLabel
                    hint="Add secondary constraints such as material, silhouette, proportions, or style. These notes refine the task prompt rather than replace it."
                    label="Reference Notes"
                  />
                  <textarea
                    className="mt-3 h-28 w-full rounded-3xl border border-white/10 bg-black/15 px-4 py-3 font-mono text-sm text-stone-100 outline-none transition placeholder:text-stone-500 focus:border-cyan-400/50 focus:ring-4 focus:ring-cyan-500/10"
                    onChange={(event) => actions.onReferenceTextChange(event.target.value)}
                    placeholder="Example: light wood finish, minimal bevels, clean modern silhouette."
                    value={model.referenceText}
                  />
                </div>

                <div className="rounded-[24px] border border-white/8 bg-white/5 p-4">
                  <HintLabel
                    hint="Upload optional reference images. They help the planner and later screenshot review loops stay aligned with your intended shape."
                    label="References"
                  />
                  <input
                    accept=".png,.jpg,.jpeg,.gif"
                    className="hidden"
                    id="reference-image-picker"
                    multiple
                    onChange={actions.onReferenceImagePick}
                    type="file"
                  />
                  <label
                    className="mt-3 inline-flex cursor-pointer items-center rounded-full border border-white/10 bg-white/8 px-4 py-2 text-sm font-medium text-stone-100 transition hover:bg-white/12"
                    htmlFor="reference-image-picker"
                  >
                    Add Reference Images
                  </label>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {model.referenceImages.length > 0 ? (
                      model.referenceImages.map((image) => (
                        <span
                          key={image}
                          className="rounded-full border border-white/8 bg-black/15 px-3 py-1 text-xs text-stone-300"
                        >
                          {image}
                        </span>
                      ))
                    ) : (
                      <span className="text-xs text-stone-500">No reference images yet.</span>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)_300px]">
                <SkeletonCard className="h-40" />
                <SkeletonCard className="h-40" />
                <SkeletonCard className="h-40" />
              </div>
            )}
          </>
        ) : null}
      </div>
    </section>
  )
}

export default memo(Composer)
