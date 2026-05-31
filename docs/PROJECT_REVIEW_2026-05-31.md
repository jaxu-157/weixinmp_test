# Vision-Triage 项目问题、优化与真实价值 Review

> 评审日期：2026-05-31  
> 范围：当前仓库文档、核心代码、测试结果、已有 benchmark 产物。  
> 结论先行：项目方向有真实价值，但当前最硬的价值不是“检测率已经很高”，而是“用多通道证据把非崩溃 UI/数据/性能故障路由到可行动维度”。文档里对 devtools 真机线的 100%/100% 表述与当前仓库产物不一致，必须降调。

## 1. 总体判断

Vision-Triage 当前更像一个“面向小程序/uni-app 的零侵入或低侵入故障分诊研究原型”，而不是一个已经成熟的通用检测器。

它已经具备三个扎实基础：

1. 有可跑通的核心诊断服务：`diagnosis/app.py` + `diagnosis/diagnose/*`，76 个诊断单元/集成测试在 `PYTHONUTF8=1` 下全部通过。
2. 有真实应用变异基准雏形：`fault_bench/bench_out/bench_report_20260530_214801.*` 和 `fault_bench/native_out/native_report_20260531_010859.*`。
3. 有明确的研究定位：不是只做 screenshot pass/fail，而是把故障分到 `visual / functional / performance` 等开发者可行动维度。

但它也有几个会直接影响答辩/论文可信度的问题：

1. 文档结论高于仓库实际证据。
2. driver 路径的性能字段命名不一致，导致性能维度静默失效。
3. benchmark 规模仍小，且部分结果低于多数类 baseline。
4. learned triage 在分布外真实截图上只有约 41%-43% 准确率，不能作为独立主力。
5. “零侵入”目前在 visual/data 上成立得更好，在 performance/业务语义上仍需要 devtools 信号或 SDK 补充。

## 2. 已确认 Bug 与风险点

### P0: driver 路径性能指标字段不一致

位置：

- `auto_test/v2_modules/driver_engine.py:156-157`
- `diagnosis/diagnose/triage.py:173-180`
- `packages/vision-triage-sdk/src/oracle.ts:26-27`

现象：

`driver_engine` 传入的是：

```python
{"interaction_ms": 900, "memory_warnings": 1}
```

但 `triage._run_performance_assertions()` 只读取：

```python
perf_data.get("interactionMs", 0)
perf_data.get("memoryWarningCount", 0)
```

我用当前代码直接验证：

```text
camel {'pass': False, 'reason': 'interaction_latency=900ms; memory_warnings=1', ...}
snake {'pass': True, 'reason': '', 'interaction_ms': 0, 'memory_warnings': 0}
```

影响：

driver/devtools 路径会把真实性能故障当作性能正常，削弱 `PerformanceRisk`、`memory_pressure`、`blocking_loop` 相关 claim。这也解释了文档里多次提到 performance 盲区。

建议：

在 `triage._run_performance_assertions()` 做兼容读取：

```python
interaction_ms = perf_data.get("interactionMs", perf_data.get("interaction_ms", 0))
memory_warnings = perf_data.get("memoryWarningCount", perf_data.get("memory_warnings", 0))
```

并补一个 regression test：snake_case 和 camelCase 都应触发性能失败。

### P0: `FINAL_REPORT.md` 引用不存在且过高的 devtools 结果

位置：

- `docs/FINAL_REPORT.md:16`
- `docs/FINAL_REPORT.md:50-51`
- `docs/FINAL_REPORT.md:103`

文档写法：

- devtools 真机：100% 检出 / 100% RCA / 0 假阳。
- 产物：`fault_bench/native_out/native_report_20260531_011309.{md,json}`。

仓库实际：

- 该 `011309` 文件不存在。
- 当前存在的最新原生报告是 `native_report_20260531_010859.*`。
- 实际结果是 recall 71%、RCA top-1 43%、macro-F1 0.39。

影响：

这是最危险的答辩风险。如果别人按仓库复核，会直接发现 headline 不可复现。

建议：

把主文档改成：

```text
devtools 真机线当前仓库可复现实跑：7 个故障 / 2 个健康对照，ours recall 71%，健康假阳 0%，RCA top-1 43%。
```

如果确实有 100% 的后续实验，应把对应报告文件补入仓库，并说明它和 `010859` 的差异。

### P1: 测试入口在 Windows 默认 GBK 下直接崩

位置：

- `diagnosis/tests/run_all.py:32,38,44,50,56,72,79`

现象：

直接运行：

```bash
python diagnosis/tests/run_all.py
```

会触发 `UnicodeEncodeError: 'gbk' codec can't encode character '\u25b6'`。

`PYTHONUTF8=1 python diagnosis/tests/run_all.py` 可通过，结果为 76/76。

建议：

入口文件里加：

```python
import sys
sys.stdout.reconfigure(encoding="utf-8")
```

或去掉特殊符号，保证 Windows 默认环境可复现。

### P1: `/diagnose` 对 malformed JSON 没有防御

位置：

- `diagnosis/app.py:241-242`
- `diagnosis/app.py:286-287`

现象：

`page_state` / `perf_data` 直接 `json.loads()`，非法 JSON 会抛异常变成 500。

影响：

自动化采集链路一旦上报坏数据，服务端没有结构化错误，测试报告难以定位。

建议：

捕获 `json.JSONDecodeError`，返回 400，并在响应里带字段名。

### P1: WeBug R2 边缘像素启发式已知会误报装饰性 UI

位置：

- `auto_test/v2_modules/webug_rules.py:51`
- `auto_test/v2_modules/webug_rules.py:128-169`
- `docs/结题报告.md:841-843`

现象：

`foreign-uniapp` 的红色渐变和左侧粗边框触发 R2 8/8 误报。文档已经记录了该事实。

建议：

R2 应优先使用 devtools 几何信号；在无 DOM 时，边缘像素 fallback 只作为低置信 evidence，不应直接进入强报警。也可以把“固定装饰边框/渐变背景”作为背景估计的排除项。

### P1: benchmark 与最终报告口径混杂

相关事实：

- `bench_report_20260530_214801`: H5 线 detection recall 60%，RCA top-1 60%，majority baseline 70%，macro-F1 0.50。
- `native_report_20260531_010859`: 原生 WXML 线 detection recall 71%，RCA top-1 43%，macro-F1 0.39。
- `diagnosis/benchmark/reports/benchmark_eval.json`: 特征级 benchmark 中 learned_forest macro-F1 0.932，但这是特征级合成/半合成评测，不等价于真实截图端到端。

风险：

文档把“特征级 benchmark 的 0.93 macro-F1”和“真实应用源码变异线”的结果放在同一叙事里，读者容易误解为真实端到端已达到 0.93。

建议：

所有 headline 必须分三类写：

1. 特征级合成/半合成 benchmark。
2. 真实 uni-app H5 源码变异。
3. 原生 WXML + devtools 真机源码变异。

每类单独报告 N、app 数、recall、FPR、RCA top-1、macro-F1。

## 3. 可优化方向

### 3.1 先统一数据协议

优先统一这些字段：

| 层 | 当前字段 | 建议 |
|---|---|---|
| SDK | `interactionMs`, `memoryWarningCount` | 保留 camelCase，对外 API 稳定 |
| Python core | 当前只读 camelCase | 同时兼容 camelCase/snake_case |
| driver/devtools | `interaction_ms`, `memory_warnings` | 输出前转换成核心协议，或核心兼容 |
| feature_extractor | `interaction_ms`, `memory_warnings` | 作为内部特征名可以保留 |

### 3.2 把性能维度从“截图后推断”改成“一等运行时信号”

当前 H5 零侵入路径抓不到 `blocking_loop`，因为截图发生在渲染完成后，画面已经稳定。性能故障不该主要依赖 SSIM。

建议：

- devtools 路径：以 `wx.getPerformance()` / `get_perf_time` / navigation wall-clock 为主。
- H5 路径：用 Playwright `performance.getEntriesByType()`、first contentful paint、long task observer。
- SDK 路径：继续用 `markInteractionStart/End` 和 memory warning。

### 3.3 把“检测”和“分诊”分开建模

现在 end-to-end RCA top-1 被 detection recall 卡住。建议报告两个指标：

- Detection recall / FPR：是否发现问题。
- Conditional RCA accuracy：在已检出的故障里，维度是否判对。

这能保留项目真正优势：在 H5 线中“检出即维度判对”的条件准确率很强，但整体 top-1 还没有赢过 majority baseline。

### 3.4 扩展样本集，而不是继续调 headline

最低建议：

- 3 个真实 app。
- 每个 app 至少 20 个源码变异。
- 每个维度至少 15 个样本。
- 每个故障都有 paired healthy control。
- 报 bootstrap 95% CI，不只报点估计。

### 3.5 降低 learned model 的主叙事权重

`learned_triage` 在特征级数据上表现好，但真实截图矩阵只有 41%-43%。它可以作为辅助通道，不适合作为当前系统主卖点。

建议主叙事改成：

```text
规则/几何/数据 token/性能信号/视觉差异的多通道 evidence fusion，比单通道更稳；learned model 是可选加权器，而不是唯一 oracle。
```

### 3.6 修复报告自动生成链路

建议为每个 benchmark 产物写一个统一 `summary.json` schema：

```json
{
  "run_id": "...",
  "app": "...",
  "n_faults": 10,
  "n_healthy": 3,
  "metrics": {
    "detection_recall": 0.6,
    "fpr": 0.0,
    "rca_top1": 0.6,
    "macro_f1": 0.5
  },
  "artifact_paths": [...]
}
```

然后文档只从该 schema 生成，避免手写 headline 和真实产物不一致。

## 4. 项目真实价值 Review

### 4.1 文档中“成立”的价值

1. **问题是真实的**：小程序/uni-app 中非崩溃故障大量存在，崩溃测试天然漏掉视觉、布局、数据绑定、性能类问题。
2. **多通道融合有增量**：H5 线中 crash-only 为 0%，whole SSIM 为 30%，tiled SSIM 为 50%，多通道为 60%；原生线中截图 43%、devtools 57%、融合 71%。
3. **分诊维度比纯检测更可行动**：OwlEye/Trident 这类工作更强调“检测/定位/描述”，本项目强调“路由到 visual / functional / performance 子系统”，这是可辩护的差异化方向。
4. **源码变异作为评测代理是合理路线**：变异测试在软件测试研究里有方法学基础，但需要诚实承认它不等同真实线上 bug 分布。

### 4.2 文档中“需要降调”的价值

1. **不能说当前 devtools 真机 100%/100%**：当前仓库证据不支持。
2. **不能说模型泛化已经好**：真实截图端到端结果显示 learned 单通道明显掉点。
3. **不能把 0.93 macro-F1 当真实端到端结论**：它来自特征级 benchmark，不是源码变异截图端到端。
4. **不能说完全零侵入覆盖所有维度**：functional/performance 的强判断仍依赖 devtools 可读信号或 SDK 语义上报。

### 4.3 最稳妥的对外 claim

建议对外这样说：

> Vision-Triage 面向小程序/uni-app 的非崩溃故障分诊，不只判断“页面坏没坏”，还把故障归因到视觉/布局、数据/功能、性能等开发者可行动维度。当前在真实第三方 uni-app H5 源码变异基准上，以 0 健康假阳检出 60% 故障；在原生 WXML + devtools 真实信号基准上，以 0 健康假阳检出 71% 故障。结果仍受小样本和检测召回限制，但多通道融合相对 crash-only、纯截图、纯 devtools 都显示出增量。

### 4.4 不建议这样说

不要说：

- “已经达到 100% 检出 / 100% RCA”。
- “超过所有前人方法”。
- “ML 模型可跨任意小程序泛化”。
- “零侵入即可完整定位功能和性能根因”。

## 5. 相比前人类似项目的优势与不足

### 5.1 对比 OwlEye / Nighthawk 类 UI display issue 检测

公开资料显示，OwlEye 基于 GUI screenshot 做 UI display issue 检测和定位，报告了 display issue 检测 precision/recall 以及定位能力。

本项目优势：

- 更贴近小程序/uni-app 运行环境，而不是泛 Android UI。
- 不只输出 display issue，而是输出根因维度。
- 可以融合 devtools 的数据 token、几何、性能信号，超出纯截图模型。

不足：

- 检测能力和样本规模远弱于这类成熟视觉检测工作。
- 对小区域低对比度故障仍容易漏检。

### 5.2 对比 Trident / Vision-driven MLLM GUI 测试

Trident 目标是检测移动 app 的非崩溃功能 bug，使用 Explorer/Monitor/Detector 多 agent，并在大规模 non-crash bug 数据上与多个 baseline 对比。

本项目优势：

- 成本更低：规则、SSIM、devtools 信号优先，MLLM 只是可选升级。
- 输出更结构化：直接给功能/视觉/性能维度，适合 CI gate 和分工派单。
- 更关注小程序平台特有信号：WXML/page.data/wx.getPerformance/scrollWidth。

不足：

- 自动探索能力弱，当前更多是矩阵/指定页面驱动。
- MLLM/cascade 的增量还没有在大规模端到端实验证明。
- 没有 Trident 那种大样本、多 baseline、消融完整度。

### 5.3 对比 WeBug / WeDetector

WeBug/WeDetector 是小程序方向最直接的 prior work。它研究了 83 个 WeChat Mini-Program bugs，并基于静态 bug pattern 检测 25 个真实小程序中的问题。

本项目优势：

- 运行时/黑盒视角更强：即使拿不到源码，也可以通过截图、page.data、几何、性能信号做诊断。
- 能覆盖视觉回归和运行时表现，这是纯静态规则较难直接验证的。
- 可以作为 WeDetector 的互补：静态提前发现风险，Vision-Triage 在运行时确认是否真的表现为用户可见问题。

不足：

- WeBug 的静态规则更精确，R2 装饰性 UI 误报说明运行时像素启发式容易受 UI 风格影响。
- 本项目当前真实 bug 覆盖来自源码变异，不是大规模 issue/PR 真实 bug。

### 5.4 对比变异测试相关工作

Just et al. FSE 2014 讨论了 mutants 是否能替代真实 faults，结论支持变异体作为测试有效性的代理，但也强调局限。

本项目优势：

- 源码变异 + paired healthy control 的路线是可辩护的。
- 变异点有明确维度标签，适合做 RCA/triage ground truth。

不足：

- 当前 N 太小。
- 变异算子偏“可见常见故障”，覆盖不了真实长尾：间歇性、纯业务逻辑、设备兼容、网络弱状态等。

## 6. 建议优先级路线图

### 一周内必须修

1. 兼容 `interactionMs` / `interaction_ms` 两套性能字段。
2. 修正文档里不存在的 `native_report_20260531_011309` 和 100% claim。
3. 修 `run_all.py` Windows 编码问题。
4. 给 `/diagnose` JSON 解析加 400 错误。
5. 给 driver performance path 增加至少 2 个 regression tests。

### 两周内建议补

1. 重新跑 H5 + 原生 devtools 两条线，生成统一 `summary.json`。
2. 补充 `detection vs conditional RCA` 指标。
3. 为 R2 视觉 fallback 加置信度，不再强报警。
4. 给 performance 故障引入 H5 Long Task / wx.getPerformance 主信号。
5. 把 `FINAL_REPORT.md` 改成“当前可复现事实版”。

### 后续研究增强

1. 扩到 3 个 app、60+ 变异。
2. 做 bootstrap CI 和 McNemar 配对检验。
3. 加真实 issue/PR bug 样本，减少“只会打自己造的 bug”的质疑。
4. 做 leave-one-channel-out 消融，证明每个通道的边际贡献。
5. 把 MLLM 只用于低置信样本，报告成本/延迟/收益三元权衡。

## 7. 本次验证记录

已执行：

```bash
python diagnosis/tests/run_all.py
```

结果：失败，原因是 Windows GBK 控制台无法输出 `▶`。

已执行：

```bash
PYTHONUTF8=1 python diagnosis/tests/run_all.py
```

结果：76/76 通过，耗时 6.66s。

已执行性能字段验证：

```python
_run_performance_assertions({"interactionMs": 900, "memoryWarningCount": 1})
_run_performance_assertions({"interaction_ms": 900, "memory_warnings": 1})
```

结果：camelCase 触发失败，snake_case 被静默当作 0，确认 bug 存在。

## 8. 外部参考

- OwlEye: https://arxiv.org/abs/2009.01417
- Trident / Seeing is Believing: https://arxiv.org/abs/2407.03037
- WeBug / WeDetector: https://wsdou.github.io/papers/2022-icse-webug.pdf
- Just et al. FSE 2014: https://homes.cs.washington.edu/~rjust/publ/JustJIEHF2014b-abstract.html

