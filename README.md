# Vision-Triage v2

基于"功能断言 + 性能断言 + 视觉断言"的微信小程序**维度化根因分诊**系统。

> **v2 升级**：v1 的手写真值表替换为可学习决策树（acc 74%→91%）；新增 cascade 视觉 oracle、350 样本 VT-Bench、可嵌入任意小程序的 SDK。
> **v2 Phase 6（最新）**：借鉴 WeBug (ICSE'22) / WeReplay (FSE'23) / MiniScope (arXiv'24) / VisionDroid (arXiv'24) 思路，新增 **driver 自动化路径 + 多通道证据融合**（learned + SSIM 基线 + WeBug 规则），多通道 OR 真实故障覆盖率 **90.9%**。
> 完整结题报告见 [`docs/结题报告.md`](docs/结题报告.md)（含项目价值边界、5 篇 prior work 调研、14-case 离线 smoke）。

## 项目定位（解决什么、不解决什么）

**目标场景** — 开发者自检解决不了的三个场景：
1. **CI / 回归批量巡检**：80 张截图 30 秒分类成 5 类 verdict
2. **黑盒验收 / 平台审核**：拿不到源码，纯输入输出黑盒分诊
3. **灰度后线上巡检**：自动巡检 + 维度归因，直接 page 对应方向

**不解决**：开发者本地单次单页面调试（这种场景用 DevTools 就行）。

## 两条使用路径

### 推荐：driver 自动化路径（0 行业务侵入）

适合黑盒验收 / CI 巡检场景。无需修改任何业务代码。

```bash
# 真实小程序（需先启动微信开发者工具 + 编译 demo-uniapp）
minitest -c auto_test/config.py -m test_cases.test_auto_matrix_v2

# 离线（用历史截图验证完整 v2 管线，不需要真小程序）
python auto_test/v2_modules/smoke_offline.py
# → 输出: auto_test/reports/v2_driver/smoke_offline_<ts>.md
```

### 可选：SDK 集成路径（精细业务语义控制）

适合开发者愿意提供 `expected/visible` 业务语义的场景。3 步集成、~14% LOC 成本。

```ts
// App.vue
installTriage(app, { backendUrl: 'http://localhost:8900' })
// 页面
const probe = useTriageProbe('home')
probe.setExpected(items.value.length)
probe.setVisible(completedCount.value)
```

## v2 新增模块速览

| 模块 | 路径 | 作用 | 阶段 |
|---|---|---|---|
| 可学习分诊 | `diagnosis/diagnose/learned_triage.py` | 18 维特征 → DecisionTree/Forest，14/14 击败规则法 12/14 | Phase 1 |
| Cascade Oracle | `diagnosis/diagnose/cascade_oracle.py` | 规则做 pre-filter，57% 不确定样本升级到 MLLM | Phase 2 |
| MLLM 重判 | `diagnosis/diagnose/mllm/` | HeuristicMLLM + DashScope Qwen-VL | Phase 2 |
| VT-Bench v1 | `diagnosis/benchmark/` | 350 样本 × 14 场景 × 25 强度 | Phase 3 |
| Vision-Triage SDK | `packages/vision-triage-sdk/` | npm 包，3 步集成 | Phase 4 |
| Sample Apps | `packages/sample-apps/{checklist,profile,search}-app/` | 13.85% LOC 集成成本 | Phase 4 |
| **稳定性等待** | `auto_test/v2_modules/stability_wait.py` | WeReplay 思路：连续帧 SSIM > 阈值再截图 | Phase 6 |
| **SSIM 基线对比** | `auto_test/v2_modules/baseline_compare.py` | SSIM + pHash + 三联可视化 diff | Phase 6 |
| **WeBug 规则** | `auto_test/v2_modules/webug_rules.py` | R1 API 无反馈 / R2 布局溢出 / R3 异步数据错配 | Phase 6 |
| **Driver Engine** | `auto_test/v2_modules/driver_engine.py` | 三通道证据融合（learned ∪ baseline ∪ webug） | Phase 6 |
| **Minium 矩阵 driver** | `auto_test/test_cases/test_auto_matrix_v2.py` | 一个 test 跑遍 3 页面 × 8 profile | Phase 6 |
| **离线 smoke** | `auto_test/v2_modules/smoke_offline.py` | 14 case 历史截图离线验证 v2 管线 | Phase 6 |

## 一键复现 v2 全部实验

```bash
cd diagnosis && pip install -r requirements.txt
cd ..

# Phase 1: 训练可学习分诊
python diagnosis/diagnose/training/train.py
python diagnosis/diagnose/training/evaluate.py     # ablation
python diagnosis/diagnose/training/smoke_test.py   # 真实截图端到端

# Phase 2: cascade oracle 评测
python diagnosis/diagnose/training/evaluate_cascade.py

# Phase 3: VT-Bench 生成与评测
python diagnosis/benchmark/generate.py --per-scenario 25
python diagnosis/benchmark/evaluate.py --oracle all

# Phase 4: SDK 集成成本审计
python packages/sample-apps/audit_integration.py

# Phase 6: v2 driver 离线 smoke（推荐先跑这条验证整条管线）
python auto_test/v2_modules/smoke_offline.py
```

输出落点：
- `diagnosis/diagnose/training/reports/`（混淆矩阵、决策树图、ablation 表）
- `diagnosis/benchmark/reports/`（VT-Bench 评测结果）
- `packages/sample-apps/integration_audit.{json,png}`
- `auto_test/reports/v2_driver/`（Phase 6 矩阵报告 + diff 图）

---

## v1 原型说明（保留）



## 项目结构

```text
vision-triage/
├── docs/                  # 项目文档
│   ├── plan.md            # 开发计划
│   └── todo.md            # 开发日志
├── demo-uniapp/           # uni-app 小程序 Demo（Vue3 + TypeScript + Vite）
│   ├── src/
│   │   ├── pages/         # 3 个演示页面
│   │   ├── components/    # 故障调试面板
│   │   └── services/      # API、故障状态、性能与 oracle 导出
│   ├── package.json
│   └── vite.config.ts
└── diagnosis/             # Python 诊断服务与 Mock API
    ├── app.py             # FastAPI 主入口
    ├── requirements.txt
    └── diagnose/          # 视觉诊断模块
```

## 环境要求

### 前端 / 小程序

- Node.js 18+ 或 20+
- npm
- HBuilderX（可选，用于“运行到微信开发者工具”）
- 微信开发者工具

### 后端

- Python 3.10+，推荐 Python 3.11 或 Conda 环境
- pip

后端依赖见 `diagnosis/requirements.txt`。

## 快速启动

建议先启动后端，再启动小程序。小程序页面数据来自本地后端 `http://localhost:8900`。

### 1. 启动 Python 后端服务

```bash
cd diagnosis
pip install -r requirements.txt
python -m uvicorn app:app --host 0.0.0.0 --port 8900 --reload
```

如果电脑上有多个 Python 环境，请先进入已经安装依赖的环境，例如 Conda：

```bash
conda activate <your-env>
cd diagnosis
python -m uvicorn app:app --host 0.0.0.0 --port 8900 --reload
```

启动成功后，浏览器打开下面地址，应返回当前故障状态：

```text
http://127.0.0.1:8900/fault/status
```

预期返回示例：

```json
{"code":0,"data":{"profile":"normal"},"profile":"normal"}
```

### 2. 启动小程序前端

本项目是 uni-app Vite/CLI 项目。可以用命令行，也可以用 HBuilderX。

#### 方式 A（推荐）：命令行编译，然后用微信开发者工具打开

```bash
cd demo-uniapp
npm install
npm run dev:mp-weixin
```

编译产物目录：

```text
demo-uniapp/dist/dev/mp-weixin
```

然后在微信开发者工具中导入该目录。

注意：这是 CLI/Vite 项目，默认输出目录是 `dist/dev/mp-weixin`，不是 HBuilderX 传统项目常见的 `unpackage/dist/dev/mp-weixin`。

#### 方式 B：HBuilderX 运行到微信开发者工具

1. 用 HBuilderX 打开 `demo-uniapp/` 目录，不要打开整个仓库根目录。
2. 菜单选择：`运行 -> 运行到小程序模拟器 -> 微信开发者工具`。
3. HBuilderX 会编译项目并拉起微信开发者工具。

如果 HBuilderX 没有自动拉起微信开发者工具，请检查：

- HBuilderX 中配置了微信开发者工具安装路径。
- 微信开发者工具已开启服务端口：`设置 -> 安全设置 -> 服务端口 -> 开启`。

## 微信开发者工具设置

为了本地调试顺利，建议在微信开发者工具中开启：

```text
详情 -> 本地设置 -> 不校验合法域名、web-view 域名、TLS 版本以及 HTTPS 证书
```

原因：

- 小程序请求本地后端 `http://localhost:8900`。
- 图片流页面使用外部图片地址 `https://picsum.photos/...`。

如果未开启该选项，可能出现接口请求失败或图片无法显示。

## Demo 页面

| 页面 | 路径 | 用途 |
|------|------|------|
| 图片流 | `pages/feed/index` | 图片模糊、白屏、加载慢 |
| 数据更新 | `pages/counter/index` | 显示旧数据、映射错误 |
| 布局压力 | `pages/layout/index` | 错位、重叠、溢出 |

右下角齿轮按钮是故障面板，可以切换故障 profile。

## 故障 Profile

| Profile | 效果 | 预期 Verdict |
|---------|------|-------------|
| `normal` | 无故障 | Pass |
| `slow_api` | 接口延迟 800-1500ms | PerformanceRisk |
| `blur_image` | 返回模糊图片 | RenderBug |
| `stale_ui` | 页面不更新显示值 | FunctionalFail |
| `wrong_mapping` | 字段映射错误 | FunctionalFail |
| `layout_overlap` | 布局错位 | RenderBug |
| `memory_pressure` | 内存压力 | PerformanceRisk |
| `mixed_fault` | 混合故障 | Mixed |

## API 端点

后端默认端口：`8900`。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/fault/status` | 查看当前故障状态 |
| POST | `/fault/activate` | 激活故障，例如 `{"profile":"slow_api"}` |
| GET | `/api/feed` | 图片流数据 |
| GET | `/api/counter` | 计数器当前值 |
| POST | `/api/counter/refresh` | 刷新计数器 |
| GET | `/api/layout` | 布局卡片数据 |
| POST | `/diagnose` | 综合诊断，上传截图和上下文 |

## 快速验证接口

启动后端后，可以在浏览器访问：

```text
http://127.0.0.1:8900/api/feed?page=1&pageSize=2
http://127.0.0.1:8900/api/counter
http://127.0.0.1:8900/api/layout
```

也可以用 curl：

```bash
curl http://127.0.0.1:8900/fault/status
curl "http://127.0.0.1:8900/api/feed?page=1&pageSize=2"
```

## 常见问题

### HBuilderX 中没有显示编译成功

优先确认打开的是 `demo-uniapp/` 目录，而不是仓库根目录。

本项目是 Vite/CLI 结构，核心文件在：

```text
demo-uniapp/src/manifest.json
demo-uniapp/src/pages.json
demo-uniapp/src/App.vue
demo-uniapp/src/main.ts
```

如果 HBuilderX 识别异常，可以改用命令行：

```bash
cd demo-uniapp
npm run dev:mp-weixin
```

然后用微信开发者工具导入：

```text
demo-uniapp/dist/dev/mp-weixin
```

### 小程序页面能打开，但图片流没有图片

通常是后端未启动，或微信开发者工具拦截了本地接口/外部图片域名。

检查步骤：

1. 浏览器访问 `http://127.0.0.1:8900/api/feed?page=1&pageSize=2`，确认后端有返回数据。
2. 微信开发者工具中开启“不校验合法域名”。
3. 重新编译或刷新小程序。

### 右下角故障面板能打开，但切换 profile 没有效果

故障面板会同步请求后端 `/fault/activate`。如果后端未启动，部分本地 UI 状态会变化，但依赖后端的故障效果不会完整生效。

## 当前完成度

- 已完成：uni-app 小程序 demo、三页演示页面、故障面板、Mock API、视觉诊断基础模块。
- 未完成完整闭环：自动化执行层、自动截图、自动提交 `/diagnose` 并生成端到端报告。