# Vision-Triage 评测协议 (EVALUATION_PROTOCOL)

> 本文件定义 Vision-Triage 的**可辩护**评测方案。核心主张不是"能检测出有问题"(detection)，而是"能把故障归因到正确的根因维度"(triage / root-cause-dimension attribution)。所有指标、基线、有效性论证都围绕这一主张设计。
>
> 适用对象：在一个**真实开源 uni-app / 微信小程序**上，对源码做受控变异(mutation)注入已知根因维度的开发者常见 bug，再用流水线判定能否归因到正确维度。
>
> 关键约束(与代码对齐 — 命名以代码中的常量为准，落地前请核对下列文件)：
> - 4 个根因维度(本协议假定): `functional / visual-render / visual-layout / performance`。判定逻辑见 `diagnosis/diagnose/triage.py` 与 `diagnosis/diagnose/cascade_oracle.py`；最终维度枚举请以这两处的常量为准。
> - 多通道诊断器(代码中已存在的通道):
>   - 视觉单项: `diagnosis/diagnose/blur.py`(模糊) / `screen.py`(黑白屏) / `layout.py`(布局-遮挡)
>   - baseline SSIM diff: `auto_test/v2_modules/baseline_compare.py`
>   - WeBug 风格规则: `auto_test/v2_modules/webug_rules.py`
>   - MLLM (Qwen-VL): `diagnosis/diagnose/mllm/dashscope_qwen_vl.py` / `qwen_vl_openai.py`
>   - 融合编排: `diagnosis/diagnose/cascade_oracle.py`
> - 故障注入器: `mitrix/generator.py`(组合故障生成) 与 `auto_test/test_fault_injection.py`。已有的 benchmark 脚手架见 `diagnosis/benchmark/generate.py` + `evaluate.py` 和 `fault_bench/vt_diagnose.py`。
> - 注：下文 §1.1 列出的 mutation 算子名(如 `blank_screen`/`blur`/`overlap`)为协议建议的统一命名；若与现有注入器字段不一致，以"故障类别→根因维度"的映射关系为准，注入器字段名可保留。

---

## 0. 术语对齐：Detection vs Triage

| 概念 | 定义 | 输出 | 对标论文 |
|---|---|---|---|
| Detection | 判断"是否有问题" | pass / fail (二分类) | OwlEye, Nighthawk, Trident |
| **Triage (本文)** | 判断"哪个**根因维度**坏了" | functional / visual-render / visual-layout / performance (4 类) | 无直接对标 → **这是 novelty 主张点** |
| RCA (服务级) | 把失败归因到具体后端服务/RPC | top-k 服务排名 | Uber Chaos (ICSE'26 SEIP) |

我们的主张落在中间层：比 Detection 多了**维度归因**，比服务级 RCA 更贴近 GUI 前端故障的开发者分诊场景。**报告中必须始终用 triage / dimension attribution 措辞，避免与 detection 论文做不公平的精度对比。**

---

## 1. Ground-Truth 故障集 (Fault Set)

### 1.1 类别 → 根因维度映射

直接复用并扩展现有注入器(`mitrix/generator.py` / `auto_test/test_fault_injection.py`)的故障类型。每个变异算子都有**唯一确定的根因维度标签**(这是 ground truth 的来源 —— 因为我们知道注入了什么)。

| # | 故障类别 (mutation operator) | 注入方法 (源码级) | 根因维度 (GT label) | 期望主导通道 |
|---|---|---|---|---|
| F1 | `blank_screen` | 注释掉 render / `v-if="false"` 隐藏根节点 | `visual-render` | screen(黑白屏) |
| F2 | `blur` | 注入 CSS `filter: blur()` | `visual-render` | blur |
| F3 | `missing_image` | 把 `<image src>` 改为坏 URL / 空值 | `visual-render` | webug_rule + screen |
| F4 | `overlap` | CSS `position:absolute` 制造组件遮挡 | `visual-layout` | layout(遮挡) |
| F5 | `broken_layout` | 破坏 flex / 错配单位(rpx↔px)致错位 | `visual-layout` | layout + ssim_diff |
| F6 | `text_overflow` | 容器宽度收缩致文本溢出/截断 | `visual-layout` | ssim_diff + webug_rule |
| F7 | `data_error` | 变异数据绑定 / 字段名 → 渲染出 `undefined`/空 | `functional` | webug_rule + ssim_diff |
| F8 | `api_fail` | 变异 API URL / 制造请求失败 | `functional` | webug_rule |
| F9 | `crash` | 注入 JS 运行时错误 | `functional` | webug_rule (error overlay) |
| F10 | `slow_load` | 注入 `setTimeout` 延迟 / 阻塞渲染 | `performance` | ssim_diff(时序) + 加载指标 |

> 注：F3/F6 若现有注入器尚未覆盖，需在 `mitrix/generator.py`(或 `auto_test/test_fault_injection.py`)中补齐 —— 这两类对齐 Nighthawk 的 missing-image / text-overlap 类目，便于跨论文对照。

### 1.2 每类样本量 (N per category)

- **目标：每个故障类别 ≥ 8 个变异实例**(在不同页面/不同组件位置注入)，10 类 → **≥ 80 个故障 mutant**。
- 维度分布(注意类不平衡，影响指标选择)：
  - functional: F7+F8+F9 ≈ 24
  - visual-render: F1+F2+F3 ≈ 24
  - visual-layout: F4+F5+F6 ≈ 24
  - performance: F10 ≈ 8 (**最稀缺类，单独标注其样本数，macro-F1 会放大它的影响**)
- **必须再加 ≥ 20 个 negative / clean 样本**(未注入故障的正常截图)，用于测假阳性率(FPR)与 pass/fail 基线。
- 规模参照：WeBug(ICSE'22) 25 个小程序、83 bug；Just et al. Defects4J 357 fault。我们 80+20 属"中等规模真实评测"区间，**在威胁有效性一节必须诚实标注 small-N**。

### 1.3 标注规程 (Labeling protocol)

借鉴 WeBug / Trident 的**多人共识 + 可复现**协议：

1. **GT 维度标签来自注入元数据**(injection-time label)：因为是受控变异，根因维度天然已知，写入 `fault_manifest.json`(字段：`fault_id, file, operator, dimension, page, inject_diff`)。
2. **可复现性校验**：每个 mutant 必须能稳定复现可见后果(截图差异),否则剔除(对标 Trident "manually reproduced")。
3. **等价变异剔除(equivalent mutant)**：若变异后截图与 baseline 无可见差异(SSIM≈1 且人工确认无差异)，判为**等价变异**并剔除 —— 这正是 Just et al. 2014 强调的不可判定问题，我们用"可见后果"操作化定义来规避。
4. **三人独立复核**(对标 Nighthawk/WeBug ≥3 reviewer)：3 名标注者独立确认 (a) 故障可见、(b) 维度标签与可见后果一致；分歧升级讨论，无法达成一致者剔除。记录 inter-rater agreement(Cohen's κ / Fleiss' κ)。
5. **配对控制(paired control)**：每个 mutant 都保留**注入前 baseline 截图**(对标 Uber Chaos "identical control test")，供 ssim_diff 通道与"是否真故障"判定使用。

---

## 2. 必须对比的基线 (Baselines)

> 规则：要主张"多通道分诊优于常规方法"，必须同时打败**平凡基线**(证明任务非平凡)和**现实基线**(证明对现有可行方案有增量)。至少 4 个，下面给 6 个。

| 基线 | 类型 | 它代表什么 | 实现 | 为什么必须比 |
|---|---|---|---|---|
| **B1 Random** | 平凡(下界) | 4 维随机猜，正确率 ~25% | 均匀随机输出一个 dimension | 证明任务有信息量；任何方法都应显著高于 25% |
| **B2 Majority / Most-Frequent-Class** | 平凡(下界) | 永远输出训练集最多的维度(如 functional) | 常数预测器 | **在类不平衡下这是最强的"作弊"基线**；macro-F1 能揭露它(它在其余 3 类 recall=0) |
| **B3 Crash/Error-Only Detector (pass/fail)** | 现实(行业现状) | 只看是否报错/崩溃 → 只能 pass/fail，**无法分诊** | 只用 `webug_rule` 的 error-overlay + JS 异常 → 把任何"fail"强制归为 functional | 代表"传统监控/崩溃上报"能力上限；对 visual-render/layout/performance 类**结构性盲区**，正好凸显 triage 价值 |
| **B4 Single-Channel Visual Oracle** | 现实(检测类 SOTA 的简化) | 单一视觉检测器(类 OwlEye/单 SSIM) | 只用 `ssim_diff` 一个通道：超阈值=fail，但维度只能映射到"visual-*"猜测 | 代表"只做视觉检测、不做维度归因"的现有视觉 oracle；用于证明**多通道融合 > 单通道** |
| **B5 MLLM-Only Free-Text Describer** | 现实(LLM 时代默认做法) | 直接把截图丢给 Qwen-VL,让它自由描述/猜原因 | 只用 `qwen_vl` 通道,prompt 不给维度 schema,自由文本→事后人工/正则映射到 4 维 | 代表"现在大家都直接问大模型"的朴素做法；用于证明**结构化多通道 > 裸 MLLM**(且暴露 MLLM 的 miscalibration / 幻觉) |
| **B6 MLLM Forced-Choice (schema)** | 现实(强 LLM 基线) | Qwen-VL 但**强制四选一** | 只用 `qwen_vl`,prompt 给定 4 维 schema,强制输出其一 | 比 B5 更强的 LLM 基线；证明"我们的增量不只是给了 schema",还来自多通道证据融合 |

**最低要求**：报告必须包含 B1、B2、B3、B4 四个；强烈建议补 B5、B6 以堵住"你不就是套了个大模型"的审稿质疑。

---

## 3. 评测指标 (Metrics)

### 3.1 主指标 (Primary — triage 质量)

对 4 个维度，把 triage 当多分类问题：

1. **Per-dimension Precision / Recall / F1**(4×3 = 12 个数,逐维度列出 —— 对标 Nighthawk per-category)。
2. **Macro-F1**(主报告数字)：4 维等权平均。**选 macro 而非 micro，因为 performance 类样本极少；macro-F1 才能惩罚"忽略小类"的 B2 majority 基线。** 同时附 micro-F1 / weighted-F1 作参考。
3. **RCA Top-1 Accuracy**：最高分维度 == GT 维度的比例(对标 Uber Chaos 的 precision@k,这里 k=1 因为维度只有 4 个)。
4. **Confusion Matrix (4×4)**：必报。揭示典型混淆(如 visual-render↔visual-layout、functional↔visual-render),指导后续改进,也是审稿人最爱看的诚实证据。

### 3.2 Triage 专属指标 (区别于纯 detection 的关键)

5. **Right-Dimension-Ranks-First (RDRF)**：流水线对每个维度都给融合分数 → 检查**正确维度是否排在第 1**。
   - 报 **Top-1 命中率** 与 **MRR (Mean Reciprocal Rank)**(对标 Just et al. fault-localization 的 MRR)。
   - MRR 比 Top-1 更细腻：即使没排第一,排第二也比排第四好,体现"分诊把开发者注意力引导到正确方向"的实际价值。
6. **Detection-vs-Triage 分解**(诚实性关键)：把端到端拆成两步并分别报：
   - **Detection accuracy**：pass/fail 是否判对(这步 B3/B4 也能做)。
   - **Conditional Triage accuracy** = P(维度正确 | 已正确判为 fail)。
   - 这样可证明:"我们的增量价值主要在**第二步**" —— 即在"已知有问题"之后，把它分到正确维度的能力，而 B3/B4 在第二步上结构性失败。

### 3.3 多通道增量 / 消融 (Ablation — 必做)

对标 Trident(去掉 bug example 致 precision -54%) 与 Nighthawk(逐类目)。

7. **Full vs Single-channel**：分别只留 1 个通道跑全集,得到 6 行单通道 macro-F1,再给 Full(6 通道融合) 一行。展示 **Full − best-single 的 ΔF1**。
8. **Leave-one-channel-out**：依次删 1 个通道,看 macro-F1 下降多少 → 量化每个通道的边际贡献(尤其证明 `qwen_vl` 是否真的有用,呼应 memory 里"Qwen 价值未证"的待办)。
9. **+Qwen vs −Qwen**:专门一组,因为 Qwen 是最贵、最受质疑的通道。**若 +Qwen 的 ΔF1 不显著为正,必须诚实写出**,并改用校准后再融合的版本。

### 3.4 统计显著性 (Significance — 区别于多数 SE 论文的加分项)

surveyed 论文里 4/5 篇 "none reported"。我们做这一项即可超越多数对照工作：

10. **McNemar test**(配对,二分类对/错):用于"Full vs 每个基线"的 Top-1 命中对错配对比较 → 报 p-value。
11. **Bootstrap 95% CI**:对 macro-F1 做 1000 次 bootstrap 重采样,给置信区间(尤其因为 N 小,点估计不可靠,CI 是诚实做法)。
12. 多基线比较时对 p 值做 **Bonferroni / Holm 校正**。

### 3.5 运维/实用指标 (Operational — 锦上添花)

13. **人工分诊节省**:对标 Uber Chaos 的 MTTR。测/估"开发者手动判定维度耗时" vs "流水线自动给维度"的时间差,即使是小样本计时实验也比纯精度有说服力。
14. **FPR on clean set**:在 20+ negative 样本上的假阳性率(误报"有故障")。

---

## 4. 有效性威胁与诚实主张 (Threats to Validity)

> 这一节决定论文能不能过审。**主动暴露**比被审稿人指出强。

### 4.1 必须预先承认的威胁

| 威胁 | 风险 | 缓解措施 / 措辞 |
|---|---|---|
| **T1 注入故障 vs 真实故障 (construct validity)** | 变异 bug 可能不代表真实开发者 bug 的分布 | **引用 Just et al. (FSE 2014)**:变异体检出能力与真实缺陷检出能力在控制覆盖率后仍**统计显著相关**,故变异体是真实缺陷的有效代理。但仍须声明"变异≠真实分布",并(若可行)补充 1-2 个来自 GitHub issue / 论坛的**真实 bug** 做外部效度锚点(对标 WeBug/Trident 的多源 GT)。 |
| **T2 自建 vs 第三方 app (external validity)** | 在自己熟悉的 app 上注入易过拟合 | 选用**第三方真实开源** uni-app/小程序(非作者编写),且(理想)**跨 ≥2 个不同 app** 验证 driver 通用性(呼应 memory 里"跨小程序通用性"已有真机证据)。明确标注 app 来源、star 数、领域。 |
| **T3 小样本 N (conclusion validity)** | 80 个 mutant 统计力有限 | 用 **bootstrap CI + McNemar** 而非只报点估计;诚实写"N=80,结论受样本规模限制,CI 已给出";不宣称跨全部小程序生态的普适性。 |
| **T4 等价变异 / FLIM (internal validity)** | 无可见后果的变异污染 GT;非故障代码被误"杀" | §1.3 的可见后果剔除 + 三人复核;借 Just et al. 措辞讨论等价变异不可判定性。 |
| **T5 维度标签主观性** | render vs layout 边界模糊 | 报 inter-rater κ;对边界类(如 F5 错位既像 render 又像 layout)在 confusion matrix 中专门讨论。 |
| **T6 MLLM 数据泄漏 / 不可复现** | Qwen-VL 可能见过该 app;输出随机 | 用注入(injection)数据集避免训练重叠(对标 Trident injection dataset);固定 temperature/seed;报多次运行方差。 |

### 4.2 可直接粘贴的诚实主张句 (Model sentences)

> 以下句子模仿 surveyed 论文的"absolute 数字 + 相对 baseline delta + 限定语"句式,填入实测数字即可。

1. **Triage novelty 句**
   > "Unlike crash/error-only detectors (B3) and single-channel visual oracles (B4) that only decide *whether* a UI is faulty, Vision-Triage further attributes each failure to its root-cause dimension (functional / visual-render / visual-layout / performance), achieving a macro-F1 of **<X>** and a Top-1 dimension accuracy of **<Y>%** on **80** source-level mutants injected into a real third-party uni-app — i.e., it answers *which dimension failed*, not merely *that something failed*."

2. **多通道融合增量句 (ablation)**
   > "Fusing six channels yields **+<Δ> macro-F1** over the best single channel and **+<Δ2>** over an MLLM-only free-text describer (B5); a leave-one-channel-out ablation shows each channel contributes a positive marginal F1, with the largest drop (**−<Δ3>**) when removing <channel>, confirming the gain comes from evidence fusion rather than any single oracle."

3. **诚实威胁句 (借 Just et al. 背书)**
   > "Our ground truth is built from systematic source-level mutation rather than field faults; following Just et al. (FSE 2014), whose study shows mutant detection correlates with real-fault detection independently of coverage, we treat mutants as a *validated proxy* for developer bugs, while explicitly noting that (a) N=80 limits statistical power — we therefore report bootstrap 95% CIs and McNemar tests rather than point estimates alone, and (b) results are anchored on real third-party app(s) but not yet generalized across the full mini-program ecosystem."

4. **实用价值句 (可选,MTTR 风格)**
   > "By auto-attributing the failing dimension, Vision-Triage reduces the manual triage step (deciding *which kind* of bug to debug) from **<a> min** to **<b> s** per failure in our timing study, directing developer attention to the correct dimension in **<MRR>** mean reciprocal rank."

---

## 5. surveyed 论文 → 借用技术映射

| surveyed paper | 借用的那一项技术 (apply to Vision-Triage) |
|---|---|
| **Nighthawk (UI display issues, 2022)** | **逐类目(per-category)报告**:每个故障类/每个维度单独给 P/R/F1,而非只给一个总分;同时报 absolute 数字 **和** 相对最佳基线的百分比 delta。 |
| **Trident / Seeing-is-Believing (2024)** | **消融即说服力**:用"删组件后指标下降多少"量化每个通道贡献(对标其去掉 bug example 致 -54%);并用 **injection dataset** 避免 MLLM 训练重叠。 |
| **Uber Chaos Testing (ICSE'26 SEIP)** | **配对控制基线(paired control)** + **precision@k / Top-1** + **MTTR(人工分诊耗时→自动)** 作为根因归因的实用主指标。 |
| **WeBug (ICSE'22)** | **多源 GT + ≥3 人专家共识标注 + 真实第三方小程序**评测;raw 检出数与外部确认率**分开报**;诚实记录假阳性成因。 |
| **Just et al. (FSE 2014)** | **变异体作为真实缺陷的有效代理**(核心效度背书) + **统计显著性(相关/Wilcoxon/McNemar)** + **MRR/Top-k** 排名指标 + 等价变异威胁的规范讨论。 |

---

## 6. 执行清单 (Checklist)

- [ ] 选定第三方真实开源 uni-app/小程序(记录来源/star/领域),理想 ≥2 个
- [ ] 在 `mitrix/generator.py`/`auto_test/test_fault_injection.py` 补齐 F3 missing_image、F6 text_overflow 算子
- [ ] 生成 80+ mutant + 20+ clean,写出 `fault_manifest.json`(含 dimension GT)
- [ ] 剔除等价变异 + 三人复核 + 记录 κ
- [ ] 实现 B1–B6 六个基线(B1/B2/B3/B4 为必做)
- [ ] 跑 Full + 6 单通道 + leave-one-out + ±Qwen 消融
- [ ] 输出:per-dim P/R/F1、macro/micro-F1、Top-1、4×4 confusion matrix、MRR、RDRF
- [ ] McNemar(Full vs 各基线)+ bootstrap 95% CI(macro-F1)+ Holm 校正
- [ ] Detection-vs-Triage 分解 + clean 集 FPR + (可选) MTTR 计时
- [ ] 按 §4.2 模板句填入实测数字,写有效性威胁段
