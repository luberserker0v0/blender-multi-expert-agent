import DeleteConfirmModal from './components/Shared/DeleteConfirmModal'
import Sidebar from './components/Sidebar/Sidebar'
import Composer from './components/Composer/Composer'
import ActivityFeed from './components/Activity/ActivityFeed'
import SettingsPanel from './components/Settings/SettingsPanel'
import InspectorPanel from './components/Inspector/InspectorPanel'
import RuntimeLogPanel from './components/RuntimeLog/RuntimeLogPanel'
import { useWorkspaceController } from './hooks/useWorkspaceController'

function App() {
  const { state, models, actions } = useWorkspaceController()

  return (
    <div className="min-h-screen overflow-hidden bg-[#1f1d1a] text-stone-100">
      <button
        className="fixed left-3 top-3 z-30 flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-[#171614] text-stone-300 shadow-xl shadow-black/20 transition hover:bg-white/10 hover:text-white lg:hidden"
        onClick={actions.sidebar.onOpenSidebar}
        type="button"
      >
        <svg aria-hidden="true" className="h-5 w-5" fill="none" viewBox="0 0 24 24">
          <path d="M4 6h16M4 12h16M4 18h16" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
        </svg>
      </button>

      <div className="relative mx-auto flex h-screen max-w-[1900px] gap-4 overflow-hidden p-3 lg:p-4">
        <Sidebar model={models.sidebar} actions={actions.sidebar} />

        <div className="flex min-w-0 flex-1 gap-4 overflow-hidden">
          <main className="flex min-h-0 min-w-0 flex-1 flex-col gap-4 overflow-hidden">
            {state.hasSessions ? (
              <>
                <Composer model={models.composer} actions={actions.composer} />
                <ActivityFeed model={models.activity} actions={actions.activity} />
              </>
            ) : (
              <section className="flex min-h-0 flex-1 items-center justify-center rounded-[28px] border border-white/8 bg-[#181715] p-8 shadow-xl shadow-black/10">
                <div className="max-w-xl text-center">
                  <p className="text-xs uppercase tracking-[0.24em] text-stone-500">Workspace</p>
                  <h2 className="mt-3 text-4xl font-semibold tracking-tight text-stone-100">Start with a new session</h2>
                  <p className="mt-4 text-sm leading-7 text-stone-400">
                    Create a session before composing a task prompt, reviewing activity, or inspecting progress history.
                  </p>
                  <button className="action-chip mt-6" onClick={actions.sidebar.onNewSession} type="button">
                    New Session
                  </button>
                </div>
              </section>
            )}
          </main>
        </div>
        <SettingsPanel model={models.settings} actions={actions.settings} />
        <InspectorPanel
          open={models.inspector.open}
          progress={models.inspector.progress}
          selectedTitle={models.inspector.selectedTitle}
          latestCapturePath={models.inspector.latestCapturePath}
          selectionKind={models.inspector.selectionKind}
          inspectorBlocks={models.inspector.inspectorBlocks}
          onClose={actions.inspector.onClose}
        />
        <RuntimeLogPanel
          open={models.runtime.open}
          runStatus={models.runtime.runStatus}
          mcpStatus={models.runtime.mcpStatus}
          consoleLog={models.runtime.consoleLog}
          mcpToolCalls={models.runtime.mcpToolCalls}
          onClose={actions.runtime.onClose}
        />
        {models.deleteModal.open ? (
          <DeleteConfirmModal
            onCancel={actions.deleteModal.onCancel}
            onConfirm={actions.deleteModal.onConfirm}
            sessionTitle={models.deleteModal.sessionTitle}
            eyebrow={models.deleteModal.eyebrow}
            description={models.deleteModal.description}
            confirmLabel={models.deleteModal.confirmLabel}
          />
        ) : null}
      </div>
    </div>
  )
}

export default App
