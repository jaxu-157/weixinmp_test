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
  navigationTiming: {}
})

export function getMetrics(): PerfMetrics {
  return metrics
}

export function markPageLoadStart(): void {
  metrics.pageLoadStart = Date.now()
}

export function markPageLoadEnd(): void {
  metrics.pageLoadEnd = Date.now()
}

export function markInteractionStart(): void {
  metrics.interactionStart = Date.now()
}

export function markInteractionEnd(): void {
  metrics.interactionEnd = Date.now()
}

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

export function initPerfObserver(): void {
  // #ifdef MP-WEIXIN
  wx.onMemoryWarning((res: any) => {
    metrics.memoryWarnings.push(Date.now())
    console.warn('[Perf] Memory warning level:', res.level)
  })

  try {
    const perf = wx.getPerformance()
    const observer = perf.createObserver((entryList: any) => {
      const entries = entryList.getEntries()
      entries.forEach((entry: any) => {
        metrics.navigationTiming[entry.name] = entry.duration || entry.startTime
      })
    })
    observer.observe({ entryTypes: ['navigation', 'render', 'script'] })
  } catch (e) {
    console.warn('[Perf] getPerformance not available:', e)
  }
  // #endif
}
