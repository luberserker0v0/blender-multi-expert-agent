import { memo, useEffect, useRef } from 'react'
import type { AgentOrchestratorModel, AgentOrchestratorResult, McpConnectionStatus, SavedSettings } from '../../types'
import { NumberField, SettingField, ToggleField } from '../ShellBits'
import HintLabel from '../Shared/HintLabel'
import PanelDrawer from '../Shared/PanelDrawer'
import { SkeletonCard } from '../Shared/Skeleton'

interface SettingsPanelProps {
  model: {
    open?: boolean
    settings: SavedSettings
    mcpStatus: McpConnectionStatus
    agentOrchestratorVerifying: boolean
    agentOrchestratorStatus: AgentOrchestratorResult | null
    agentOrchestratorModels: AgentOrchestratorModel[]
    agentOrchestratorModelsLoading: boolean
    agentOrchestratorModelsError: string
  }
  actions: {
    onSettingsUpdate: (updater: SavedSettings | ((prev: SavedSettings) => SavedSettings)) => void
    onClose: () => void
    onVerifyAgentOrchestrator: () => void
    onRefreshAgentOrchestratorModels: () => void
    onSaveSettings: () => void
  }
}

function SettingsPanel({ model, actions }: SettingsPanelProps) {
  const yoloFileRef = useRef<HTMLInputElement | null>(null)
  const lastModelLoadKeyRef = useRef('')

  useEffect(() => {
    if (!model.open) return
    const url = String(model.settings?.agentOrchestratorUrl ?? '').trim()
    if (!url) return
    const key = `${url}::${model.settings?.agentOrchestratorModel ?? ''}`
    if (lastModelLoadKeyRef.current === key) return
    lastModelLoadKeyRef.current = key
    actions.onRefreshAgentOrchestratorModels()
  }, [actions, model.open, model.settings?.agentOrchestratorModel, model.settings?.agentOrchestratorUrl])

  return (
    <PanelDrawer open={model.open ?? true} onClose={actions.onClose} title="Environment Defaults" subtitle="Settings">
      {model.settings ? (
        <div className="space-y-5">
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0 flex-1">
                <SettingField
                  hint="Base URL of the Agent Orchestrator service used for model discovery, readiness checks, and multi-expert runs."
                  label="Agent Orchestrator URL"
                  onChange={(value) => actions.onSettingsUpdate((current) => ({ ...current, agentOrchestratorUrl: value }))}
                  value={model.settings.agentOrchestratorUrl}
                />
              </div>
              <button
                className="action-chip mt-6 whitespace-nowrap disabled:cursor-not-allowed disabled:opacity-50"
                disabled={model.agentOrchestratorVerifying || !String(model.settings.agentOrchestratorUrl ?? '').trim()}
                onClick={actions.onVerifyAgentOrchestrator}
                type="button"
              >
                {model.agentOrchestratorVerifying ? 'Verifying...' : 'Verify AO'}
              </button>
            </div>
          </div>
          <div className="rounded-2xl border border-white/8 bg-white/5 px-3 py-3 text-sm text-stone-300">
            <div className="flex items-center justify-between gap-3">
              <HintLabel
                hint="Shows whether the bridge can reach Agent Orchestrator with the current URL."
                label="Agent Orchestrator Status"
              />
              <span className={`rounded-full px-2 py-1 text-[11px] uppercase ${model.agentOrchestratorStatus?.ok ? 'bg-emerald-500/15 text-emerald-300' : 'bg-amber-500/15 text-amber-300'}`}>
                {model.agentOrchestratorStatus?.ok ? 'ready' : 'pending'}
              </span>
            </div>
            <p className="mt-2 text-xs text-stone-500">
              {model.agentOrchestratorStatus?.message || 'The UI verifies Agent Orchestrator automatically when you enter a session.'}
            </p>
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <HintLabel
                hint="Models are loaded from Agent Orchestrator. Select one for new runs; conversation IDs are created and managed by this project."
                label="Agent Orchestrator Model"
              />
              <button
                className="rounded-full border border-white/8 bg-white/5 px-3 py-1.5 text-xs font-semibold text-stone-300 transition hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                disabled={model.agentOrchestratorModelsLoading || !String(model.settings.agentOrchestratorUrl ?? '').trim()}
                onClick={actions.onRefreshAgentOrchestratorModels}
                type="button"
              >
                {model.agentOrchestratorModelsLoading ? 'Loading...' : 'Refresh'}
              </button>
            </div>
            <select
              className="w-full rounded-2xl border border-white/10 bg-black/15 px-3 py-2 text-sm text-stone-100 outline-none focus:border-amber-400/50"
              disabled={model.agentOrchestratorModelsLoading || model.agentOrchestratorModels.length === 0}
              onChange={(event) => actions.onSettingsUpdate((current) => ({ ...current, agentOrchestratorModel: event.target.value }))}
              value={model.settings.agentOrchestratorModel}
            >
              <option value="">
                {model.agentOrchestratorModels.length > 0 ? 'Use Agent Orchestrator default' : 'Load models from Agent Orchestrator'}
              </option>
              {model.agentOrchestratorModels.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.id}
                </option>
              ))}
            </select>
            <p className="text-xs leading-5 text-stone-500">
              {model.agentOrchestratorModelsError ||
                (model.agentOrchestratorModels.length > 0
                  ? `${model.agentOrchestratorModels.length} models available from Agent Orchestrator.`
                  : 'No model list loaded yet.')}
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <NumberField
              hint="Maximum seconds the bridge waits for Agent Orchestrator requests before treating them as failed."
              label="AO Timeout"
              onChange={(value) => actions.onSettingsUpdate((current) => ({ ...current, agentOrchestratorTimeoutSeconds: value }))}
              value={model.settings.agentOrchestratorTimeoutSeconds}
            />
            <NumberField
              hint="Maximum refinement rounds allowed for individual part work before the run stops or asks for correction."
              label="Part Rounds"
              onChange={(value) => actions.onSettingsUpdate((current) => ({ ...current, maxPartRefinementRounds: value }))}
              value={model.settings.maxPartRefinementRounds}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <NumberField
              hint="Maximum assembly review rounds allowed after parts are built."
              label="Assembly Rounds"
              onChange={(value) => actions.onSettingsUpdate((current) => ({ ...current, maxAssemblyRounds: value }))}
              value={model.settings.maxAssemblyRounds}
            />
          </div>
          <ToggleField
            checked={model.settings.keepAgentOrchestratorConversation}
            hint="Keeps the AO conversation workspace after a run for debugging instead of destroying it automatically."
            label="Keep AO Conversation"
            onChange={(checked) => actions.onSettingsUpdate((current) => ({ ...current, keepAgentOrchestratorConversation: checked }))}
          />
          <ToggleField
            checked={model.settings.useYoloValidation}
            hint="Enables YOLO-based perception checks during validation when a local YOLO model path is configured."
            label="Use YOLO Validation"
            onChange={(checked) => actions.onSettingsUpdate((current) => ({ ...current, useYoloValidation: checked }))}
          />
          <div className="space-y-2">
            <HintLabel
              hint="Paste a full local path if the model lives anywhere on disk. The browser file picker can only reveal the selected filename, so Browse is a helper, not a full native path chooser."
              label="YOLO Model Path"
            />
            <div className="flex gap-2">
              <input
                className="flex-1 rounded-2xl border border-white/10 bg-black/15 px-3 py-2 text-sm text-stone-100 outline-none focus:border-amber-400/50"
                onChange={(event) => actions.onSettingsUpdate((current) => ({ ...current, yoloModelPath: event.target.value }))}
                value={model.settings.yoloModelPath}
              />
              <button className="action-chip whitespace-nowrap" onClick={() => yoloFileRef.current?.click()} type="button">
                Browse...
              </button>
              <input
                accept=".pt,.onnx,.engine"
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0]
                  if (!file) return
                  actions.onSettingsUpdate((current) => ({ ...current, yoloModelPath: file.name }))
                }}
                ref={yoloFileRef}
                type="file"
              />
            </div>
          </div>
          <div className="rounded-3xl border border-white/8 bg-white/5 p-4">
            <HintLabel
              hint="Blender MCP runs on the backend machine and is always required for new runs. This panel is read-only so the frontend stays aligned with the deployed server configuration."
              label="Blender MCP Status"
            />
            <div className="mt-3 rounded-2xl bg-black/30 px-4 py-3 text-xs text-stone-100">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium uppercase tracking-[0.18em] text-stone-500">Connection</p>
                  <p className="mt-1 text-sm text-stone-100">
                    {model.mcpStatus.server_name ? `${model.mcpStatus.server_name}: ` : ''}
                    {model.mcpStatus.message}
                  </p>
                  <p className="mt-2 text-xs text-stone-400">
                    Tools detected: {model.mcpStatus.tools.length}
                  </p>
                </div>
                <span className="rounded-full bg-white/8 px-2 py-1 text-[11px] uppercase text-stone-300">
                  {model.mcpStatus.state}
                </span>
              </div>
            </div>
          </div>
          <button className="action-chip w-full justify-center" onClick={actions.onSaveSettings} type="button">
            Save Settings
          </button>
        </div>
      ) : (
        <div className="space-y-5">
          <SkeletonCard className="h-12" />
          <SkeletonCard className="h-20" />
          <SkeletonCard className="h-12" />
          <div className="grid grid-cols-2 gap-3">
            <SkeletonCard className="h-16" />
            <SkeletonCard className="h-16" />
          </div>
          <SkeletonCard className="h-40" />
          <SkeletonCard className="h-48" />
        </div>
      )}
    </PanelDrawer>
  )
}

export default memo(SettingsPanel)
