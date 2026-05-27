# profile-app — Vision-Triage SDK 集成样例 (2)

第二个集成样例：用户资料 + 统计 + 头像加载场景，比 checklist-app 更接近真实业务页面。
重点演示：当业务里有"加载远程数据 + 显示在多个 widget"时，probe 如何对齐 expected/visible。

## 集成成本测量

| 文件 | 集成行数 | 业务行数 | 集成占比 |
|---|---|---|---|
| `src/main.ts` | 4 行 | 7 行 | 36% |
| `src/pages/profile/index.vue` | 7 行 | 86 行 | 7.5% |
| **合计** | **11 行** | **93 行** | **10.6%** |

与 checklist-app 一致——集成成本基本与业务规模脱钩，是常数级别。

## 支持的故障 profile

| profile | 期望 verdict |
|---|---|
| normal | Pass |
| slow_api | PerformanceRisk（加载延迟） |
| stale_ui | FunctionalFail（点击刷新后名字仍是空） |
| wrong_mapping | FunctionalFail（接口字段错误） |
| blur_image | RenderBug（头像图模糊） |
| layout_overlap | RenderBug（头像和文字重叠） |
| memory_pressure | PerformanceRisk |
| mixed_fault | Mixed |

profile-app 因为有头像、统计、文字三类元素，**8 个 profile 全部可激活**——这是 checklist-app 没有的覆盖能力。

## 数据来源

为了避免对真实后端有依赖，本样例的 `loadProfile()` 用 `setTimeout(200)` 模拟一个加载延迟。
实际项目里替换为 `uni.request({ url: ... })` 即可。
