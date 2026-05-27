# Vision-Triage SDK 集成指南

把"功能 + 性能 + 视觉"三模态分诊能力嵌入到任意 uni-app / 微信小程序项目，只需三步。

## 1. 安装

```bash
# 假设你的项目和 vision-triage-sdk 在同一个 monorepo
npm install vision-triage-sdk
# 或用 file: 协议
npm install file:../vision-triage-sdk
```

## 2. 在 main.ts 调用一次 installTriage

```ts
import { createSSRApp } from 'vue'
import App from './App.vue'
import { installTriage } from 'vision-triage-sdk'

export function createApp() {
  const app = createSSRApp(App)
  installTriage(app, {
    backendUrl: 'http://localhost:8900',  // Vision-Triage 后端
    autoSyncFault: true,                  // 自动从后端拉取 fault profile
    perfObserver: true,                   // 启用 wx.getPerformance + onMemoryWarning
  })
  return { app }
}
```

## 3. 在每个想被分诊的页面用 useTriageProbe

```vue
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useTriageProbe } from 'vision-triage-sdk'

const probe = useTriageProbe('counter')   // page name 任意，但要在自动化脚本里能对上

const expected = ref(0)
const display = ref(0)

async function refresh() {
  probe.markInteractionStart()
  const res = await fetch('/api/counter').then(r => r.json())
  expected.value = res.data.value
  display.value = res.data.value      // 业务逻辑：这里如果有 stale_ui 会保持旧值
  probe.markInteractionEnd()

  probe.setExpected(expected.value)   // 告诉 SDK 期望值
  probe.setVisible(display.value)     // 告诉 SDK 实际可见值
}
</script>
```

## 集成完成后，发生了什么？

- `useTriageProbe` 返回的 probe 会自动维护页面级状态
- SDK 在全局挂了一个 `__visionTriage.getPageState('counter')`，自动化层可以隔空拿
- 性能数据（页面加载、交互延迟、内存告警次数）自动收集
- 调用后端 `POST /diagnose` 时，把 `probe.exportState()` 序列化进 `page_state` 字段即可

## 完整集成成本估算

| 项目 | 代码量 |
|---|---|
| main.ts 安装 | 4 行 |
| 每个页面的 probe | 2~6 行 |
| package.json 依赖 | 1 行 |

按 5 个页面算，**总集成成本 < 30 行**。

## 触发分诊（自动化层）

后端依然走原来的端点；自动化脚本里只需要在调用 `/diagnose` 时把 `probe.exportState()` 拼进去：

```python
state = automator.evaluate(
  "() => globalThis.__visionTriage.getPageState('counter')"
).result.value
requests.post(f"{BACKEND}/diagnose", files={"screenshot": img}, data={
    "page_type": "counter",
    "page_state": json.dumps(state["pageState"]),
    "perf_data": json.dumps(state["perfData"]),
})
```

## 选择分诊引擎

后端 `/diagnose` 支持 `engine` 参数：
- `rule` — 规则法 truth table（baseline）
- `learned` — 决策树模型（默认）
- `cascade` — 规则 → MLLM 级联

也可以用 `/diagnose/compare` 同时返回两个引擎的结果，方便 A/B。
