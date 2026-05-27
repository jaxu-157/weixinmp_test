# search-app — Vision-Triage SDK 集成样例 (3)

带有"搜索结果列表 + 跳转详情"的多页面场景。
重点演示：多页面 probe 共存（globalThis.__visionTriage 支持跨页面查询）。

## 集成成本测量

| 文件 | 集成行数 | 业务行数 |
|---|---|---|
| `src/main.ts` | 4 | 7 |
| `src/pages/search/index.vue` | 8 | 70 |
| `src/pages/detail/index.vue` | 6 | 28 |
| **合计** | **18** | **105** |

## 支持的故障 profile

| profile | 期望 verdict |
|---|---|
| normal | Pass |
| slow_api | PerformanceRisk |
| stale_ui | FunctionalFail（搜索后结果数与 expected 不一致） |
| wrong_mapping | FunctionalFail |
| memory_pressure | PerformanceRisk |
| mixed_fault | Mixed |
