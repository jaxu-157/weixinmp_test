/** App 级别安装：configure backend + 启动性能观察器 + 自动 sync fault */
import type { App } from 'vue'
import { configureFault, syncFromServer } from './fault'
import { initPerfObserver } from './perf'
import type { InstallOptions } from './types'

let installed = false

export function installTriage(app: App | null, options: InstallOptions): void {
  if (installed) {
    console.warn('[vision-triage-sdk] already installed')
    return
  }
  installed = true

  const opts: Required<InstallOptions> = {
    backendUrl: options.backendUrl,
    autoSyncFault: options.autoSyncFault ?? true,
    perfObserver: options.perfObserver ?? true,
    debug: options.debug ?? false,
  }

  configureFault({ backendUrl: opts.backendUrl, debug: opts.debug })

  if (opts.perfObserver) {
    initPerfObserver()
  }

  if (opts.autoSyncFault) {
    // 异步触发首次同步；不 await，避免阻塞 createApp
    syncFromServer().catch(() => { /* ignore */ })
  }

  // 提供给 app.provide，便于在没有用 composable 的场合也能拿到配置
  if (app && typeof app.provide === 'function') {
    app.provide('vision-triage-options', opts)
  }
}
