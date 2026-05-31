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
  // 切 profile 时先把所有 flag 复位，避免上一次残留污染本次（例如 blur 漏到 slow_api）
  state.currentProfile = profile
  state.latencyMs = 0
  state.blurLevel = 0
  state.staleEnabled = false
  state.overlapEnabled = false
  state.memoryPressure = false

  // 解析复合故障（如 "blur_image+slow_api"）；保留 mixed_fault 作为遗留组合别名
  const parts = profile.split('+')

  for (const part of parts) {
    switch (part) {
      case 'normal':
        break
      case 'slow_api':
        state.latencyMs = Math.max(state.latencyMs, 1200)
        break
      case 'blur_image':
        state.blurLevel = 10
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
        state.latencyMs = Math.max(state.latencyMs, 1000)
        state.staleEnabled = true
        state.memoryPressure = true
        break
    }
  }
}

export function resetFault(): void {
  activateFault('normal')
}

export async function syncFromServer(): Promise<void> {
  return new Promise((resolve) => {
    uni.request({
      url: 'http://127.0.0.1:8900/fault/status',
      method: 'GET',
      success: (res) => {
        const data = res.data as any
        const serverProfile = data?.data?.profile || data?.profile
        if (serverProfile && serverProfile !== state.currentProfile) {
          activateFault(serverProfile as FaultProfile)
        }
        resolve()
      },
      fail: () => {
        resolve()
      }
    })
  })
}
