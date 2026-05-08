import { reactive } from 'vue'

export type FaultProfile =
  | 'normal'
  | 'slow_api'
  | 'blur_image'
  | 'stale_ui'
  | 'wrong_mapping'
  | 'layout_overlap'
  | 'memory_pressure'
  | 'mixed_fault'

export interface FaultState {
  currentProfile: FaultProfile
  latencyMs: number
  blurLevel: number
  staleEnabled: boolean
  overlapEnabled: boolean
  memoryPressure: boolean
}

const state = reactive<FaultState>({
  currentProfile: 'normal',
  latencyMs: 0,
  blurLevel: 0,
  staleEnabled: false,
  overlapEnabled: false,
  memoryPressure: false
})

export function getFaultState(): FaultState {
  return state
}

export function activateFault(profile: FaultProfile): void {
  state.currentProfile = profile
  switch (profile) {
    case 'normal':
      state.latencyMs = 0
      state.blurLevel = 0
      state.staleEnabled = false
      state.overlapEnabled = false
      state.memoryPressure = false
      break
    case 'slow_api':
      state.latencyMs = 1200
      break
    case 'blur_image':
      state.blurLevel = 5
      break
    case 'stale_ui':
      state.staleEnabled = true
      break
    case 'wrong_mapping':
      break
    case 'layout_overlap':
      state.overlapEnabled = true
      break
    case 'memory_pressure':
      state.memoryPressure = true
      break
    case 'mixed_fault':
      state.latencyMs = 1000
      state.staleEnabled = true
      state.memoryPressure = true
      break
  }
}

export function resetFault(): void {
  activateFault('normal')
}
