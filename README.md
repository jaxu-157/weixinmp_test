# Vision-Triage v2

> 三种测试流程速览（2026-05-27 更新）

## 环境

```bash
conda activate vision-triage
# 若输出含中文/emoji 报 GBK 错，在前面加 PYTHONIOENCODING=utf-8
```

## 三种测试一览

| 编号 | 测试 | 命令 | 目标 |
|------|------|------|------|
| ① | **Auto Test** 一键自动化 | `python run_auto_test.py` | demo-uniapp |
| ② | **Mitrix** 组合故障 × 多标签 | `python run_mitrix_test.py` | demo-uniapp |
| ③ | **Foreign Matrix** 陌生小程序零侵入 | `python auto_test/v2_modules/run_foreign_matrix.py --project third-wxapp-mall --tag wxapp --repeat 2 --qwen` | 第三方 |

> ① 和 ② 互不影响，独立运行。① 是 8 个预定义 profile 单一判决矩阵；② 是组合故障生成 + 多标签检测。

### ① Auto Test：一键自动化测试

8 个预定义故障 profile，自动启动后端 → 连接 Minium → 执行矩阵 → 生成报告。

```bash
python run_auto_test.py
```

**输出：** `reports/auto_test_report_*.json` + `reports/auto_test_matrix_*.txt`

---

### ② Mitrix：组合故障注入 × 多标签诊断

自动生成组合测试用例（6 单故障 + 15 两两组合 + 3 三故障），每故障独立检测签名，输出 Precision/Recall/F1。

```bash
python run_mitrix_test.py
```

**输出：** `auto_test/reports/mitrix_fault_detection_matrix_*.json`

---

### ③ Foreign Matrix：陌生小程序零侵入验证

对第三方小程序验证零侵入 attach + 健康页假阳率。

```bash
python auto_test/v2_modules/run_foreign_matrix.py --project third-wxapp-mall --tag wxapp --repeat 2 --qwen
```

**前置：**
- 微信开发者工具可以关闭（脚本自动启动）
- **脚本启动后，将新打开的微信开发者工具窗口保持屏幕最前**（否则截图失败）
- Qwen API Key 在 `qwen.md` 中：`api-key：sk-xxx`

**输出：** `auto_test/reports/v2_driver/wxapp_foreign_*.json` + `.md`

---

## 修复记录（2026-05-27）：Foreign Matrix 假阳率 100% → 0%

**问题：** 第三方稀疏小程序页面（wxapp-mall）的 verdict 假阳率 75%（无 qwen） / 50%（有 qwen），webug 假阳率 75%。

**根因 + 修复：**

| 文件 | 位置 | 问题 | 修改 |
|------|------|------|------|
| `diagnosis/diagnose/cascade_oracle.py` | `_is_confident_zone` | 稀疏页面 `bw=True` 直接判 fail，Qwen 被跳过 | `bw=True` 且 `blur>30` 时升级给 Qwen |
| 同上 | `analyze` L113 | `black_white` OR 拼接，Qwen 纠正被规则覆盖 | 高置信度时完全由 Qwen 覆盖 |
| 同上 | `analyze` L116-119 | Qwen 说清晰但 blur_score 仍低，ML 模型被误导 | Qwen 判清晰时 blur_score 拉到 ≥400 |
| `auto_test/v2_modules/webug_rules.py` | bands | 顶部/底部边缘带被 navbar/tabBar 填满 | 仅保留左右边缘带 |
| 同上 | `_estimate_bg_color` | 四角采样被角落内容干扰 | 改为全图中位数 |
| 同上 | 阈值 | 0.18 太敏感 | 提高到 0.60 |

**效果：**

| 指标 | 修复前（无 qwen） | 修复前（有 qwen） | 修复后（有 qwen） |
|------|:---:|:---:|:---:|
| verdict 假阳率 | 75% | 50% | **0%** |
| baseline 假阳率 | 0% | 0% | **0%** |
| webug 假阳率 | 75% | 75% | **0%** |
| 任一通道假阳率 | 100% | 75% | **0%** |

---

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

## 测试路径

三行命令，一行一个测试（详见顶部三种测试一览）：

```bash
python run_auto_test.py                                                      # 一键自动化
python run_mitrix_test.py                                                    # 组合故障矩阵
python auto_test/v2_modules/run_foreign_matrix.py --project third-wxapp-mall --tag wxapp --repeat 2 --qwen
```

也支持离线 smoke（用历史截图验证管线，不需要真小程序）：

```bash
python auto_test/v2_modules/smoke_offline.py
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

## 上游实验复现（需训练数据）

> 以下为上游 v2 各 Phase 实验脚本，部分需要历史截图/training 数据。日常测试只需顶部三种。

```bash
# Phase 1: 训练可学习分诊（需训练数据）
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

## 项目结构

```text
├── run_auto_test.py               # ① 一键自动化测试
├── run_mitrix_test.py             # ② 组合故障矩阵
├── auto_test/
│   ├── config.py                  # Minium/开发者工具配置
│   ├── v2_modules/
│   │   ├── run_foreign_matrix.py  # ③ 陌生小程序零侵入
│   │   ├── run_real_matrix.py     # 页面×故障多通道矩阵
│   │   ├── driver_engine.py       # 三通道诊断引擎
│   │   ├── baseline_compare.py    # SSIM/pHash 基线对比
│   │   ├── webug_rules.py         # WeBug R1/R2/R3 规则
│   │   ├── stability_wait.py      # 帧稳定性等待
│   │   └── smoke_offline.py       # 离线 smoke 验证
│   ├── test_cases/                # 测试用例
│   └── reports/                   # 测试报告输出
├── mitrix/                        # 组合故障注入引擎
│   ├── engine.py                  # 信号检测引擎
│   ├── generator.py               # 组合用例生成
│   └── runner.py                  # 测试执行器
├── diagnosis/
│   ├── app.py                     # FastAPI 诊断后端
│   └── diagnose/
│       ├── triage.py              # 规则法分诊
│       ├── learned_triage.py      # 决策树 ML 分诊
│       ├── cascade_oracle.py      # 规则→Qwen-VL 级联
│       ├── feature_extractor.py   # 18 维特征提取
│       ├── screen.py              # 黑/白屏检测
│       ├── blur.py / layout.py / ocr.py
│       └── mllm/                  # MLLM 适配器（Qwen-VL / Heuristic）
├── demo-uniapp/                   # 本项目小程序（集成故障 hook）
├── third-wxapp-mall/              # 第三方小程序（零侵入验证目标）
├── docs/                          # 项目文档
├── qwen.md                        # Qwen API Key
└── .gitignore
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

```bash
conda activate vision-triage
python run_auto_test.py        # 或 run_mitrix_test.py / foreign matrix
```

脚本自动启动后端、连接微信开发者工具、执行测试、生成报告。前置条件：

- 微信开发者工具已安装（`config.py` 中 `_find_dev_tool_cli()` 自动探测路径）
- demo-uniapp 已编译：`cd demo-uniapp && npm run dev:mp-weixin`（仅 ① ② 需要）
- 若输出含中文/emoji 报 GBK 错，在前面加 `PYTHONIOENCODING=utf-8`

### 手动启动后端（调试用）

```bash
python -m uvicorn diagnosis.app:app --host 0.0.0.0 --port 8900
# 验证: http://127.0.0.1:8900/fault/status → {"code":0,"data":{"profile":"normal"}}
```

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

- 已完成：三条自动化测试线（一键自动化 / 组合故障矩阵 / 陌生小程序零侵入验证）
- 诊断引擎：规则法 + 决策树 ML + Qwen-VL 级联 oracle + SSIM 基线 + WeBug 三规则
- 6 类原子故障注入（blur / slow / stale / wrong_mapping / layout_overlap / memory）及其组合
- 第三方小程序零侵入假阳率：0%（2026-05-27 修复后）