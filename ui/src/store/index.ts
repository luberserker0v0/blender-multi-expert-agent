import { defaultSettings } from '../data/sampleSession'
import { createWorkspaceStore } from './useWorkspaceStore'

export const useWorkspaceStore = createWorkspaceStore(defaultSettings)
