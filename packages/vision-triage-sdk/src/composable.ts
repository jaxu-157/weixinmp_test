/** 主公开 API：useTriageProbe 给页面用 */
import { ref, onUnmounted } from 'vue'
import {
  markPageLoadStart,
  markPageLoadEnd,
  markInteractionStart,
  markInteractionEnd,
  resetMetrics,
} from './perf'
import { buildOracleOutput } from './oracle'
import type { ProbeOptions, TriageProbe, UiFlags } from './types'

/** SDK 内部维护的"所有活跃 probe"注册表，供后端通过自动化驱动统一查询。 */
const _registry = new Map<string, TriageProbe>()

export function getRegistry(): Map<string, TriageProbe> {
  return _registry
}

export function useTriageProbe(pageName: string, options?: ProbeOptions): TriageProbe {
  const visible = ref<any>(undefined)
  const expected = ref<any>(undefined)
  const uiFlags = ref<UiFlags>({
    hasOverlap: false,
    imageLoaded: true,
    isBlank: false,
    ...(options?.defaultUiFlags || {}),
  })

  markPageLoadStart()

  const probe: TriageProbe = {
    pageName,
    setVisible(v) { visible.value = v },
    setExpected(v) { expected.value = v },
    setUiFlag(flag, v) { uiFlags.value[flag] = v },
    markInteractionStart() { markInteractionStart() },
    markInteractionEnd() { markInteractionEnd() },
    markPageLoadStart() { markPageLoadStart() },
    markPageLoadEnd() { markPageLoadEnd() },
    exportState() {
      return buildOracleOutput(pageName, visible.value, expected.value, uiFlags.value)
    },
  }

  _registry.set(pageName, probe)

  // 暴露到全局，让 miniprogram-automator 能跨页面查询
  try {
    // @ts-ignore - getApp 是小程序运行时全局
    const _getApp: any = typeof (globalThis as any).getApp === 'function' ? (globalThis as any).getApp : null
    const g: any = typeof globalThis !== 'undefined' ? globalThis :
                   _getApp ? _getApp().globalData : null
    if (g) {
      g.__visionTriage = g.__visionTriage || {}
      g.__visionTriage.getPageState = (name: string) => {
        const p = _registry.get(name)
        return p ? p.exportState() : null
      }
      g.__visionTriage.listProbes = () => Array.from(_registry.keys())
    }
  } catch (e) { /* ignore */ }

  onUnmounted(() => {
    _registry.delete(pageName)
    resetMetrics()
  })

  return probe
}
