# 已核实事实清单（写报告唯一数字来源 — 任何数字必须出自此文件，禁止臆造）

> 每个数字都已从产物 JSON 逐字段读出（2026-05-31）。写三份文档时只准引用本文件数字。
> 本文件没有的数字 → 写"未测/不适用"，不准编。

## 0. 中期状态（来自 中期报告.pptx，实读 10 页）
- 标题：**基于视觉感知的小程序性能根因诊断系统**；组员：许畅 贾续 单子豪
- 核心创新（中期已提出概念）：**三重断言分诊**——Afunc 功能断言 / Aperf 性能断言 / Avisual 视觉断言（"决策矩阵"为开题预想）
- 载体：**仅 demo 小程序**（demo-uniapp，图片流 feed / 数据更新 counter / 布局压力 layout 三板块）
- 故障注入方式：后端 8900 端口 `/fault/activate` 切 Profile（URL 加 blur=5 参数等），8 种 Profile
- 性能数据：**硬编码推断（900ms）**（中期自己列为问题："未覆盖真实交互耗时"）
- layout 重叠模块：**已开发但未接入 triage 决策**（中期自列缺口）
- 实测规模：**自动化跑了 3 项测试，2 成功(slow_api/memory_pressure) 1 失败(blur_image)**；blur 阈值需精调
- **中期没有：真实第三方 app、源码变异基准、统计置信区间、根因定位实测、跨页、诚实负结果**
- 中期"下一步计划"立的指标：blur/layout 诊断准确率 100%、接真实 wx.getPerformance、8 Profile 全覆盖、误诊率↓≥30%

## 1. 系统架构（核对代码）
- **一个诊断引擎 + 两条取信号路径**（不是两套系统）
- 诊断引擎：`fault_bench/vt_diagnose.py` / `diagnosis/diagnose/triage.py`，三轴 = 视觉/功能/性能
- 路径①「不用 devtools / H5」：`fault_bench/bench/renderer.py`（Playwright 无头渲染 uni-app 编译的 H5）+ `run_campaign.py`；信号 = 分块 SSIM(8×3, 阈值0.85) + 整图 SSIM + DOM 几何。→ A/B/D 线。
- 路径②「用 devtools / 真机」：`auto_test/v2_modules/devtools_probe.py`（minium connect 零侵入只读）；信号 = `page.data` + `wx.getPerformance` + 元素真几何 `scrollWidth`。→ C 线。
- 互补：H5 全自动可大样本但有数据/性能盲区；devtools 补数据/几何盲区但样本小、需手开开发者工具。

## 2. 检测 + 分诊（四条证据线，全部逐字段核对产物）

| 线 | 产物文件 | 载体 | N | ours检出 | 健康假阳 | crash-only | 条件RCA(检出即对) |
|---|---|---|---|---|---|---|---|
| A H5随机大样本 | campaign_20260531_033057 | 小兔鲜儿 uni-app | 20故障/5健康 | **50%** [CI 30–70%] | **0%** | **0%** | **8/10=0.80** |
| B H5手挑 | bench_report_20260530_214801 | 小兔鲜儿 | 10故障/3健康 | **60%** | **0%** | **0%** | **5/6=0.833** |
| C devtools真机 | native_report_20260531_010859 | youzouzou 原生WXML | 7故障/2健康 | **71.4%** | **0%** | crash-only 42.9%(健康假阳50%) | **3/5=0.60** |
| D 跨页 | crosspage_20260531_061419 | index/cart/my | 5故障/12健康 | 2/5 检出 | **0/12** | — | 2/2 |

### A 线分项（campaign_20260531_033057）
- 整图 SSIM 20% / 分块 SSIM 50% / ours(多通道) 50% / crash-only 0% / RCA top-1 40% / 条件RCA 8/10=0.80。
- bootstrap 95% CI = [30%, 70%]。

### B 线分项（bench_report_20260530_214801）
- ours 检出 60% / 假阳 0% / crash-only 0% / RCA top-1 60% / **条件RCA 5/6=0.833**。
- （注：旧报告曾误写 6/6，产物真值是 5/6=0.833。）

### C 线分项（native_report_20260531_010859，逐通道）
- **ours 多通道 recall 71.4%（5/7），健康假阳 0%**。
- 子通道：devtools-only 57.1%(4/7,假阳0%) / screenshot-only 42.9%(3/7) / crash-only 42.9%(3/7,**健康假阳50%**)。
- RCA top-1 42.9% / **条件RCA 3/5=0.60**。
- （注：旧报告曾把"57%"当 C 线检出——那其实是 devtools-only 子通道 57.1%；ours 多通道是 71.4%。旧报告"4/4"错，真值 3/5。）
- C 线意义：devtools 路径(page.data/真几何)抓到 H5 截图漏的数据/几何故障；crash-only 在纯色页假阳 50%，反衬 ours 0 假阳。

### D 线稳定性（mystab/stability.json + cart_stability.json）
- index / my / cart **三页干净渲染两两分块 SSIM 全 = 1.0**（cart 低于0.85的对数 = 0）→ 三页确定性渲染，0 假阳非偶然。

## 3. 根因定位（本轮新增，确定性无 LLM）

| 能力 | 产物文件 | 结果 |
|---|---|---|
| 视觉→源文件（单点 hash，旧） | localization_v2 | 4/10 = 40% |
| 视觉→源文件（bbox 面积排序，新） | localization_v2 | **文件级 8/10 = 80%；组件级 9/10 = 90%** |
| 功能 字段→源码行（给定坏字段名） | field_line | **5/5 = 100%** exact |
| 功能 page.data坏字段→源码行（端到端闭环，离线合成数据） | datafield_loop | **4/4 = 100%** |

- 视觉定位链路：分块SSIM最低tile集 → 与所有元素 getBoundingClientRect 求交叠面积 → 面积最大且非根容器的元素 → data-v hash → .vue 源文件。
- 修法①：用 **data-v hash**（每.vue唯一不撞车）而非 class（被 uni 框架 wrapper 类污染）；hash→文件 6/6 全对。
- 修法②：**bbox 面积排序** 替代单点 elementsFromPoint（单点命中相邻/大容器）；4/10→8/10。
- 视觉定位 3 步迭代：0/10(class) → 4/10(hash+单点) → 8/10(hash+bbox)。
- 字段→行 5/5 实测行号：XtxGuess item.name→L64 / item.price→L67；HotPanel item.title→L15 / item.alt→L16；CategoryPanel item.name→L20。
- page.data闭环 4/4：guessList[0].price→L67、name→L64、HotPanel alt→L16、CategoryPanel name→L20（合成 page.data 驱动；真机换成 minium page.data 即端到端，真机验证待做）。
- **平台不对称（诚实）**：字段名运行时恢复在 minium 原生路径直接（page.data 结构化命名坏字段，`devtools_probe.collect_data` 新增 `suspicious_fields`/`broken_field_paths`）；H5 prod 编译掉 `{{ }}`、Vue per-node 实例不可达，H5 路径字段名运行时恢复仍是缺口。

## 4. 诚实负结果（方法学严谨的体现，全部实测）
- **R1 性能维 H5 零侵入 = 负结果**：注入 onLoad 阻塞 1.4s，墙钟 time-to-content delta 同一注入两次 1359ms vs 172ms（方差>注入量，不可复现）；headless Long Task API 对 1.4s 阻塞只报 ~80ms；FCP 不变。→ H5 零侵入检测不到主线程阻塞，性能维是盲区。
- **R2 残留 FPR 根因 = 跨构建基线（非轮播抖动）**：同会话/同构建 FPR 0%；旧 build 的 baseline vs 新 build 渲染整体 SSIM ~0.49 → 跨构建混用产物全假阳。已修（同构建取样）。
- **Qwen-VL 单图 = 系统性偏见**：对带纹理占位图，每张（含健康基线）都判 has_missing_image=True → 100% 检出是假象、健康页 100% 误报。差分融合（图+基线+代码）消除偏见但太保守（recall 30%）。→ Qwen 当前不可用作视觉检测通道；正确用法是"已定位区域的解释器"非"检测器"。
- 性能定位若要做：CDP Profiler（Playwright newCDPSession 可驱动）+ source-map 给函数+行级，确定性；但 H5 检测是前提（盲区卡住），原生微信深 CPU profiler 是 GUI-only（minium 拿不到）。

## 5. 工程质量
- 测试：`diagnosis/tests/run_all.py` → **82/82 通过**。
- 评测方法学：真实第三方 app + 源码变异（变异即真值，Just et al. FSE'14）+ 配对健康对照 + 混合池 + bootstrap 95% CI。
- 定位链路全确定性、零 LLM 调用（grep 确认）。
- git：dev 分支，已 push origin。

## 6. 相对中期"简单缝合"的真实增量
1. demo→**真实第三方开源 app**（小兔鲜儿 uni-app + youzouzou 原生）+ 源码变异基准 + bootstrap CI（中期实测仅 3 项、性能 900ms 硬编码、准确率"待补充"→ 现在 A 线 50%[CI30-70%]/0假阳 等可复现数字）
2. "三重断言概念"→**真信号驱动的三轴分诊**（中期 perf 硬编码、layout 未接入；现在 C 线接真 wx.getPerformance/page.data/真几何，layout 已接入）
3. 规则匹配根因→**源文件/源码行级定位**（视觉 8/10、字段→行 5/5、page.data 闭环 4/4）
4. 单 demo 单截图通道→**双路径架构**（H5 + devtools 互补盖盲区）+ 跨页 + 每页稳定性门控
5. 无评测→**一批诚实负结果**（Qwen 偏见、性能盲区、跨构建 FPR），证明方法学严谨
