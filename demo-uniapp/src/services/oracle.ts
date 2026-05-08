import { getFaultState, type FaultProfile } from './fault'
import { getMetrics, getPageLoadDuration, getInteractionDuration } from './perf'

export interface PageState {
  page: string
  visibleValue?: any
  expectedValue?: any
  updatedAt: number
  faultProfile: FaultProfile
  uiFlags: {
    hasOverlap: boolean
    imageLoaded: boolean
    isBlank: boolean
  }
}

export interface OracleOutput {
  pageState: PageState
  perfData: {
    pageLoadMs: number
    interactionMs: number
    memoryWarningCount: number
    navigationTiming: Record<string, number>
  }
  timestamp: number
}

export function exportPageState(
  pageName: string,
  visibleValue?: any,
  expectedValue?: any,
  uiFlags?: Partial<PageState['uiFlags']>
): OracleOutput {
  const fault = getFaultState()
  const metrics = getMetrics()

  const output: OracleOutput = {
    pageState: {
      page: pageName,
      visibleValue,
      expectedValue,
      updatedAt: Date.now(),
      faultProfile: fault.currentProfile,
      uiFlags: {
        hasOverlap: uiFlags?.hasOverlap ?? false,
        imageLoaded: uiFlags?.imageLoaded ?? true,
        isBlank: uiFlags?.isBlank ?? false
      }
    },
    perfData: {
      pageLoadMs: getPageLoadDuration(),
      interactionMs: getInteractionDuration(),
      memoryWarningCount: metrics.memoryWarnings.length,
      navigationTiming: { ...metrics.navigationTiming }
    },
    timestamp: Date.now()
  }

  return output
}
