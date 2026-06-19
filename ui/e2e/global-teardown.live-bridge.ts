import { copyFileSync, existsSync, renameSync, rmSync, unlinkSync } from 'fs'
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

async function restoreFile(backupPathname: string, pathname: string) {
  if (existsSync(backupPathname)) {
    await retryFsMutation(() => copyFileSync(backupPathname, pathname))
    await retryFsMutation(() => unlinkSync(backupPathname))
  } else if (existsSync(pathname)) {
    await retryFsMutation(() => unlinkSync(pathname))
  }
}

async function globalTeardown() {
  const repoRoot = path.resolve(__dirname, '../../')
  const runtimeRoot = path.join(repoRoot, 'data', 'runtime')
  const runtimeGuiDir = path.join(runtimeRoot, 'gui')

  const savedSettingsPath = path.join(runtimeGuiDir, 'saved_settings.json')
  const savedSettingsBackup = path.join(runtimeGuiDir, 'saved_settings.json.e2e-live-backup')
  const uiStatePath = path.join(runtimeGuiDir, 'ui_state.json')
  const uiStateBackup = path.join(runtimeGuiDir, 'ui_state.json.e2e-live-backup')
  const sessionDataPath = path.join(runtimeRoot, 'session_data')
  const sessionDataBackup = path.join(runtimeRoot, 'session_data.e2e-live-backup')

  await restoreFile(savedSettingsBackup, savedSettingsPath)
  await restoreFile(uiStateBackup, uiStatePath)

  try {
    if (existsSync(sessionDataPath)) {
      await retryFsMutation(() => rmSync(sessionDataPath, { recursive: true, force: true }))
    }
  } catch {
    // Best-effort cleanup for Windows when the bridge process is still releasing file handles.
  }
  try {
    if (existsSync(sessionDataBackup) && !existsSync(sessionDataPath)) {
      await retryFsMutation(() => renameSync(sessionDataBackup, sessionDataPath))
    }
  } catch {
    // Keep teardown resilient when prior cleanup already restored the directory.
  }
}

export default globalTeardown
