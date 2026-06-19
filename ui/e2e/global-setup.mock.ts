import { existsSync, copyFileSync, mkdirSync, writeFileSync } from 'fs'
import { fileURLToPath } from 'url'
import path from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

async function globalSetup() {
  const repoRoot = path.resolve(__dirname, '../../')
  const runtimeGuiDir = path.join(repoRoot, 'data', 'runtime', 'gui')
  const savedSettingsPath = path.join(runtimeGuiDir, 'saved_settings.json')
  const savedSettingsBackup = path.join(runtimeGuiDir, 'saved_settings.json.e2e-backup')

  mkdirSync(runtimeGuiDir, { recursive: true })

  if (existsSync(savedSettingsPath)) {
    copyFileSync(savedSettingsPath, savedSettingsBackup)
  }

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
}

export default globalSetup
