/** Vision-Triage SDK 顶层导出
 *
 * 三步集成契约：
 *
 *   // 1. 在 main.ts 调用 installTriage
 *   import { installTriage } from 'vision-triage-sdk'
 *   const app = createApp(App)
 *   installTriage(app, { backendUrl: 'http://localhost:8900' })
 *
 *   // 2. 在每个想被分诊的页面用 useTriageProbe
 *   import { useTriageProbe } from 'vision-triage-sdk'
 *   const probe = useTriageProbe('counter')
 *   probe.setExpected(serverValue)
 *   probe.setVisible(displayValue)
 *
 *   // 3. 跑测试时直接拿后端的 /diagnose 端点（无需改业务代码）
 */

export { installTriage } from './install'
export { useTriageProbe, getRegistry } from './composable'
export { buildOracleOutput } from './oracle'
export {
  activateFault,
  resetFault,
  getFaultState,
  syncFromServer,
  configureFault,
} from './fault'
export {
  markPageLoadStart,
  markPageLoadEnd,
  markInteractionStart,
  markInteractionEnd,
  getInteractionDuration,
  getPageLoadDuration,
  getMetrics,
  resetMetrics,
  initPerfObserver,
} from './perf'

export type {
  FaultProfile,
  UiFlags,
  PageState,
  PerfData,
  OracleOutput,
  InstallOptions,
  ProbeOptions,
  TriageProbe,
} from './types'
