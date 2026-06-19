import { copyFileSync, existsSync, unlinkSync } from 'fs'
import { fileURLToPath } from 'url'
import path from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

async function globalTeardown() {
  const repoRoot = path.resolve(__dirname, '../../')
  const runtimeGuiDir = path.join(repoRoot, 'data', 'runtime', 'gui')
  const savedSettingsPath = path.join(runtimeGuiDir, 'saved_settings.json')
  const savedSettingsBackup = path.join(runtimeGuiDir, 'saved_settings.json.e2e-backup')

  if (existsSync(savedSettingsBackup)) {
    copyFileSync(savedSettingsBackup, savedSettingsPath)
    unlinkSync(savedSettingsBackup)
  }
}

export default globalTeardown
