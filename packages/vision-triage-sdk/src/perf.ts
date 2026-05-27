/** 性能指标采集 */
import { reactive } from 'vue'

export interface PerfMetrics {
  pageLoadStart: number
  pageLoadEnd: number
  interactionStart: number
  interactionEnd: number
  memoryWarnings: number[]
  navigationTiming: Record<string, number>
}

const metrics = reactive<PerfMetrics>({
  pageLoadStart: 0,
  pageLoadEnd: 0,
  interactionStart: 0,
  interactionEnd: 0,
  memoryWarnings: [],
  navigationTiming: {},
})

export function getMetrics(): PerfMetrics {
  return metrics
}

export function markPageLoadStart(): void { metrics.pageLoadStart = Date.now() }
export function markPageLoadEnd(): void { metrics.pageLoadEnd = Date.now() }
export function markInteractionStart(): void { metrics.interactionStart = Date.now() }
export function markInteractionEnd(): void { metrics.interactionEnd = Date.now() }

export function getPageLoadDuration(): number {
  if (!metrics.pageLoadStart || !metrics.pageLoadEnd) return 0
  return metrics.pageLoadEnd - metrics.pageLoadStart
}

export function getInteractionDuration(): number {
  if (!metrics.interactionStart || !metrics.interactionEnd) return 0
  return metrics.interactionEnd - metrics.interactionStart
}

export function resetMetrics(): void {
  metrics.pageLoadStart = 0
  metrics.pageLoadEnd = 0
  metrics.interactionStart = 0
  metrics.interactionEnd = 0
  metrics.memoryWarnings = []
  metrics.navigationTiming = {}
}

/** 注册微信平台的性能观察器（仅 MP-WEIXIN 有效）。 */
export function initPerfObserver(): void {
  // @ts-ignore - wx 全局仅在小程序运行时存在
  const _wx = typeof wx !== 'undefined' ? wx : null
  if (!_wx) return

  try {
    _wx.onMemoryWarning((res: any) => {
      metrics.memoryWarnings.push(Date.now())
      console.warn('[vision-triage-sdk:perf] memory warning level=', res?.level)
    })
  } catch (e) { /* not supported on this platform */ }

  try {
    const perf = _wx.getPerformance && _wx.getPerformance()
    if (perf && perf.createObserver) {
      const observer = perf.createObserver((entryList: any) => {
        const entries = entryList.getEntries()
        entries.forEach((entry: any) => {
          metrics.navigationTiming[entry.name] = entry.duration || entry.startTime
        })
      })
      observer.observe({ entryTypes: ['navigation', 'render', 'script'] })
    }
  } catch (e) { /* ignore */ }
}
