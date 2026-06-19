import { copyFileSync, existsSync, mkdirSync, renameSync, rmSync, writeFileSync } from 'fs'
import { fileURLToPath } from 'url'
import path from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function isRetryableFsError(error: unknown) {
  if (!(error instanceof Error)) return false
  return /EBUSY|EPERM|EACCES/i.test(error.message)
}

async function retryFsMutation(action: () => void, attempts = 20, delayMs = 250) {
  let lastError: unknown
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      action()
      return
    } catch (error) {
      lastError = error
      if (!isRetryableFsError(error) || attempt === attempts - 1) {
        throw error
      }
      await delay(delayMs)
    }
  }
  throw lastError
}

async function backupFile(pathname: string, backupPathname: string) {
  if (existsSync(pathname)) {
    await retryFsMutation(() => copyFileSync(pathname, backupPathname))
  }
}

async function globalSetup() {
  const repoRoot = path.resolve(__dirname, '../../')
  const runtimeRoot = path.join(repoRoot, 'data', 'runtime')
  const runtimeGuiDir = path.join(runtimeRoot, 'gui')

  const savedSettingsPath = path.join(runtimeGuiDir, 'saved_settings.json')
  const savedSettingsBackup = path.join(runtimeGuiDir, 'saved_settings.json.e2e-live-backup')
  const uiStatePath = path.join(runtimeGuiDir, 'ui_state.json')
  const uiStateBackup = path.join(runtimeGuiDir, 'ui_state.json.e2e-live-backup')
  const sessionDataPath = path.join(runtimeRoot, 'session_data')
  const sessionDataBackup = path.join(runtimeRoot, 'session_data.e2e-live-backup')

  mkdirSync(runtimeGuiDir, { recursive: true })

  await backupFile(savedSettingsPath, savedSettingsBackup)
  await backupFile(uiStatePath, uiStateBackup)

  if (existsSync(sessionDataBackup)) {
    await retryFsMutation(() => rmSync(sessionDataBackup, { recursive: true, force: true }))
  }
  if (existsSync(sessionDataPath)) {
    await retryFsMutation(() => renameSync(sessionDataPath, sessionDataBackup))
  }
  mkdirSync(sessionDataPath, { recursive: true })

  writeFileSync(
    savedSettingsPath,
    JSON.stringify(
      {
        agent_orchestrator_base_url: 'http://127.0.0.1:4111',
        agent_orchestrator_model: '',
        agent_orchestrator_destroy_on_finish: true,
        agent_orchestrator_timeout_seconds: 120,
        max_part_refinement_rounds: 3,
        max_assembly_rounds: 3,
        use_yolo_perception: false,
        yolo_model_path: '',
        yolo_viewpoints: ['front'],
      },
      null,
      2,
    ),
    'utf-8',
  )

  writeFileSync(
    uiStatePath,
    JSON.stringify(
      {
        current_session_id: '',
        sessions: [],
        workspaces: {},
      },
      null,
      2,
    ),
    'utf-8',
  )
}

export default globalSetup
