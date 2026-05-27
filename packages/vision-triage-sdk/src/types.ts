/** Vision-Triage SDK 公开类型 */

export type FaultProfile =
  | 'normal'
  | 'slow_api'
  | 'blur_image'
  | 'stale_ui'
  | 'wrong_mapping'
  | 'layout_overlap'
  | 'memory_pressure'
  | 'mixed_fault'
  | string  // 允许用户扩展自己的 profile

export interface UiFlags {
  hasOverlap: boolean
  imageLoaded: boolean
  isBlank: boolean
}

export interface PageState {
  page: string
  visibleValue?: any
  expectedValue?: any
  updatedAt: number
  faultProfile: FaultProfile
  uiFlags: UiFlags
}

export interface PerfData {
  pageLoadMs: number
  interactionMs: number
  memoryWarningCount: number
  navigationTiming: Record<string, number>
}

export interface OracleOutput {
  pageState: PageState
  perfData: PerfData
  timestamp: number
}

export interface InstallOptions {
  /** Vision-Triage 后端地址，例：'http://localhost:8900' */
  backendUrl: string
  /** 自动从后端拉取 fault profile，默认 true */
  autoSyncFault?: boolean
  /** 启动微信性能监听（getPerformance + onMemoryWarning），默认 true */
  perfObserver?: boolean
  /** 调试日志，默认 false */
  debug?: boolean
}

export interface ProbeOptions {
  /** 自定义 UI flag 默认值 */
  defaultUiFlags?: Partial<UiFlags>
}

export interface TriageProbe {
  pageName: string
  setVisible<T>(value: T): void
  setExpected<T>(value: T): void
  setUiFlag(flag: keyof UiFlags, value: boolean): void
  markInteractionStart(): void
  markInteractionEnd(): void
  markPageLoadStart(): void
  markPageLoadEnd(): void
  exportState(): OracleOutput
}
