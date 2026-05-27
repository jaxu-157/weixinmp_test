/** 页面状态打包器：把当前 SDK 内部状态打包成 OracleOutput */
import { getFaultState } from './fault'
import { getMetrics, getPageLoadDuration, getInteractionDuration } from './perf'
import type { OracleOutput, UiFlags } from './types'

export function buildOracleOutput(
  pageName: string,
  visibleValue: any,
  expectedValue: any,
  uiFlags: UiFlags,
): OracleOutput {
  const fault = getFaultState()
  const metrics = getMetrics()

  return {
    pageState: {
      page: pageName,
      visibleValue,
      expectedValue,
      updatedAt: Date.now(),
      faultProfile: fault.currentProfile,
      uiFlags: { ...uiFlags },
    },
    perfData: {
      pageLoadMs: getPageLoadDuration(),
      interactionMs: getInteractionDuration(),
      memoryWarningCount: metrics.memoryWarnings.length,
      navigationTiming: { ...metrics.navigationTiming },
    },
    timestamp: Date.now(),
  }
}
