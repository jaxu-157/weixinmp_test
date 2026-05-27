# checklist-app — Vision-Triage SDK 集成样例

一个最小的待办清单小程序，演示如何在三步内把 Vision-Triage 三模态分诊嵌入到一个全新的 uni-app 项目。

## 集成成本测量

| 文件 | 集成行数 | 业务行数 | 集成占比 |
|---|---|---|---|
| `src/main.ts` | 4 行 (`installTriage`) | 6 行 | 40% |
| `src/pages/home/index.vue` | 8 行（`useTriageProbe` + 3 处 `mark*` + 1 处 `set*`） | 96 行 | 7.7% |
| **合计** | **12 行** | **102 行** | **10.5%** |

集成行数标准：只数因为加 SDK 才新增的代码，包括 import、调用 SDK API、把状态同步给 probe。

## 支持的故障 profile

通过后端 `/fault/activate` 可以激活：

| profile | 在 checklist 页表现 | 期望 verdict |
|---|---|---|
| normal | 无故障 | Pass |
| slow_api | 任何依赖网络的操作变慢 | PerformanceRisk |
| stale_ui | 切换后页面不更新 | FunctionalFail |
| memory_pressure | 大量任务时触发 | PerformanceRisk |

(visual 类故障 `blur_image` / `layout_overlap` 与本页面业务关联较弱，不强制覆盖。)

## 验证步骤

1. `pnpm i` 安装依赖
2. 启动后端：`uvicorn diagnosis.app:app --port 8900`
3. 把本目录用微信开发者工具打开，启用真机/模拟器
4. 自动化层走 `auto_test_runner` 的同一套流程，唯一区别是 page name 用 `checklist_home`
