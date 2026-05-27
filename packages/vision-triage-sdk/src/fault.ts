/** Fault profile 状态管理（SDK 内部） */
import { reactive } from 'vue'
import type { FaultProfile } from './types'

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
  memoryPressure: false,
})

let backendUrl = 'http://localhost:8900'
let debugMode = false

function log(...args: any[]) {
  if (debugMode) console.log('[vision-triage-sdk:fault]', ...args)
}

export function configureFault(opts: { backendUrl: string; debug?: boolean }) {
  backendUrl = opts.backendUrl
  debugMode = !!opts.debug
}

export function getFaultState(): FaultState {
  return state
}

export function activateFault(profile: FaultProfile): void {
  state.latencyMs = 0
  state.blurLevel = 0
  state.staleEnabled = false
  state.overlapEnabled = false
  state.memoryPressure = false
  state.currentProfile = profile

  switch (profile) {
    case 'normal':
      break
    case 'slow_api':
      state.latencyMs = 1200
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
      state.latencyMs = 1000
      state.staleEnabled = true
      state.memoryPressure = true
      break
    default:
      // 用户扩展的 profile：保持 normal flag 状态，profile 字符串透传
      break
  }
  log('activated', profile)
}

export function resetFault(): void {
  activateFault('normal')
}

export async function syncFromServer(): Promise<void> {
  return new Promise((resolve) => {
    // @ts-ignore  uni-app/小程序运行时全局
    const requester = typeof uni !== 'undefined' ? uni.request : (typeof wx !== 'undefined' ? wx.request : null)
    if (!requester) {
      log('no uni/wx.request available, skip sync')
      resolve()
      return
    }
    requester({
      url: `${backendUrl}/fault/status`,
      method: 'GET',
      success: (res: any) => {
        const data = res.data
        const serverProfile = data?.data?.profile || data?.profile
        if (serverProfile && serverProfile !== state.currentProfile) {
          activateFault(serverProfile as FaultProfile)
        }
        resolve()
      },
      fail: () => {
        log('sync failed (backend offline?)')
        resolve()
      },
    })
  })
}
