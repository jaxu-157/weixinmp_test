# 真实开源小程序 · 源码变异故障注入 × 维度根因分诊 —— 基准与汇报

> 本轮工作的**最终汇报核心**。回答三件事：
> 1. 在**真实第三方开源 uni-app** 上做**源码变异故障注入**，Vision-Triage 能不能诊断出被改坏的代码？
> 2. 怎么**论证它比常规方法（crash 测试 / 单通道）更有效**？（方法学见 [`EVALUATION_PROTOCOL.md`](EVALUATION_PROTOCOL.md)）
> 3. 找到的**真实有用场景**是什么。
>
> **所有数字来自实跑产物** `fault_bench/bench_out/bench_report_20260530_214801.{md,json}`，未做任何美化。

---

## 0. 一句话结论（诚实版）

> 在真实开源电商小程序「小兔鲜儿」上，把 10 个常见开发者错误**注入源码、重新编译、headless 渲染**：
> - **常规 crash/错误测试检出 0/10** —— 视觉/布局/数据类非崩溃故障对它**完全不可见**。
> - **Vision-Triage 零侵入（仅截图+DOM+计时）在保守阈值下检出 6/10（60%）、健康页 0 假阳**；
>   其中**被检出的故障，根因维度 100% 判对（6/6）**——它一旦报警，就能告诉你该查哪一类子系统。
> - 关键工程改进：把视觉回归从**整图 SSIM（30%）升级为分块 SSIM（50%，阈值放宽到 0.95 可达 90%）**。

**真实有用的场景** = **跨端（uni-app）小程序的 CI 视觉根因门禁（zero-touch visual RCA gate）**：
PR 一来自动编译 H5、headless 截图、与基线**分块比对 + 维度分诊**——不仅告诉你"页面坏了"，还告诉你
"坏在**渲染/布局**、还是**数据绑定**、还是**性能**"，把开发者定位成本从"全页排查"降到"按维度排查"。
常规 CI 的崩溃/lint 门禁对这类非崩溃故障**零覆盖**，这是真实空白。

---

## 1. 为什么这个实验能成立（效度）

| 设计点 | 做法 | 杀掉的威胁 |
|---|---|---|
| 真实第三方代码 | 载体 = GitHub 开源 `Megasu/uniapp-shop-vue3-ts`（小兔鲜儿），**非自建** | "为讨好检测器而造 app" 的 artifact |
| 只改源码、不改检测器 | 每个故障 = 1 处 `old→new` 源码替换，编译后渲染 | 注入与检测耦合 |
| 变异即真值 | 注入点维度已知即标签（Just et al. FSE'14：变异是真实缺陷的有效代理） | "注入≠真实故障" |
| 配对健康对照 | 故障渲染配同页同数据健康渲染算 SSIM；另跑 3 次健康复诊测假阳 | 把差异严格归因到注入改动（Uber Chaos 同款 paired-control） |
| 全自动可复现 | uni-app→H5 静态编译→Playwright headless→诊断，无人工、无微信开发者工具 | 真机截图 flaky（历史教训）、不可复现 |

> 后端（itheima mock API）已下线（502），用 Playwright 路由拦截 + 本地 data-URI 图喂 fixtures：
> **被测的 UI/布局/绑定代码 100% 是第三方真实代码，只有数据是固定桩**（标准做法，不削弱效度）。

## 2. 故障集（10 个常见开发者错误 → 已知根因维度）

| # | 故障 id | 维度 | 改了什么（真实常犯错误） |
|---|---|---|---|
| 1 | guess_missing_image | visual | 商品图 `:src` 绑定丢失 → 大面积缺图 |
| 2 | swiper_missing_image | visual | 轮播大图 `:src` 丢失 → 顶部 banner 缺图 |
| 3 | guess_invisible_text | visual | 商品名颜色写成近白色（白卡片上）→ 文字不可见（对比度） |
| 4 | guess_item_overflow | layout→visual | 卡片宽 345rpx→720rpx → 双列网格水平溢出 |
| 5 | guess_image_oversize | layout→visual | 商品图 304rpx→900rpx → 撑破卡片 |
| 6 | hot_cards_nowrap | layout→visual | 热门区去掉 flex 换行 → 多图挤一行溢出 |
| 7 | hot_image_oversize | layout→visual | 热门图 150rpx→760rpx → 撑破面板格子 |
| 8 | guess_price_nan | functional | 价格用不存在的 `item.count` 参与计算 → 渲染 `NaN` |
| 9 | guess_name_empty | functional | 商品名绑错字段 `item.title` → 名称全空（硬样本，无异常 token） |
| 10 | guess_blocking_loop | performance | 组件 setup 同步死循环 1.4s → 首屏阻塞 |

注入器/打分器：`fault_bench/bench/mutations.py`、`run_bench.py`；诊断包装 `fault_bench/vt_diagnose.py`。

## 3. 结果（实测，阈值 0.85 保守操作点）

**检测层（ours vs 常规基线）** — 召回@故障(N=10) / 假阳@健康(3)：

| 方法 | 检出召回 | 健康假阳 | 含义 |
|---|---|---|---|
| crash_only（崩溃/JS 异常/黑白屏） | **0%** | 0% | 非崩溃故障对崩溃测试**完全不可见** |
| verdict_only（learned 五分类单通道） | 0% | 0% | 单看分类器不够 |
| ssim_whole_only（**整图** SSIM，项目原通道） | **30%** | 0% | 整图 SSIM 把局部改动稀释到阈值之上→漏 |
| ssim_tiled_only（**分块** SSIM，本轮新增） | **50%** | 0% | 分块恢复局部敏感度（同阈值 1.7× 整图） |
| webug_only（R2/R3 规则） | 10% | 0% | 仅抓 DOM 溢出/异常 token |
| **ours（多通道并集 + 分诊）** | **60%** | **0%** | — |

**根因分诊层（维度 RCA）**：

- **RCA Top-1 = 60%**，**低于"永远猜 visual"的多数类基线 70%**（诚实声明）——因为 **RCA 被检测召回卡住**：
  没检出的故障无法分维度。
- **但条件于"已检出"，维度判定 6/6 = 100% 正确**（5 visual + 1 functional 全部判对）。
  → 正确的卖点不是"分类准确率高"，而是**"一旦报警，路由 100% 指对子系统"**——这正是 triage 的价值。
- macro-F1 = 0.50；visual P=1.00 R=0.71 F1=0.83；functional P=1.00 R=0.50 F1=0.67；performance R=0（见局限）。
  注：两类 precision 均为 1.00（检出的 6 个无一误判维度），印证"检出即指对子系统"。

**视觉通道阈值扫描**（`fault_bench/bench/sweep.py`，健康对照 tile-SSIM 全为 1.0）：

| tile 阈值 | 分块单通道召回 | 多通道召回 | 健康假阳 |
|---|---|---|---|
| 0.85（保守默认） | 50% | 60% | 0% |
| 0.90 | 80% | 90% | 0% |
| 0.95 | 80% | 90% | 0% |
| 0.99 | 90% | 90% | 0% |

> 解读：H5 健康重渲染是**确定性的（3 个健康对照 tile-SSIM 全 = 1.0）**，所以阈值放到 0.99 仍 **0 假阳**、
> 多通道检出冲到 **90%**。**但真实 app 的健康基线非确定性**（动画/广告/时间戳），0.95+ 偏乐观，故**默认仍用保守 0.85**；
> 真实部署应按目标 app 的健康基线分布自校准阈值（标准视觉回归做法）。这条扫描是为了诚实展示通道有上限空间，
> **不是**把 0.95 当成 headline。逐用例 tile-SSIM 见 §3 末与 `sweep.py` 输出。

**逐用例**（whole=整图SSIM, tiled=最差分块SSIM；阈值 0.85）：

| 故障 | 维度 | 检出 | 判定维度 | whole | tiled | 备注 |
|---|---|---|---|---|---|---|
| guess_missing_image | visual | ✅ | visual ✓ | 0.81 | **0.53** | 大面积缺图 |
| swiper_missing_image | visual | ✅ | visual ✓ | 0.96(整图漏) | **0.65** | 分块救回 |
| guess_item_overflow | visual | ✅ | visual ✓ | 0.82 | **0.48** | |
| guess_image_oversize | visual | ✅ | visual ✓ | 0.85 | **0.61** | |
| hot_cards_nowrap | visual | ✅ | visual ✓ | 0.94(整图漏) | **0.69** | 分块救回 |
| guess_price_nan | functional | ✅ | functional ✓ | 0.996 | 0.98 | 靠 WeBug-R3 抓 `NaN` token |
| guess_invisible_text | visual | ❌ | — | 0.98 | 0.90(近阈值) | 不可见文字改动太小 |
| hot_image_oversize | visual | ❌ | — | 0.97 | 0.86(近阈值) | 单格撑破，改动占比小 |
| guess_name_empty | functional | ❌ | — | 0.98 | 0.90(近阈值) | 空绑定无 token，像素改动小 |
| guess_blocking_loop | performance | ❌ | — | 1.0 | 1.0 | 渲染完才截图，零侵入计时抓不到 |

> 3 个视觉/数据漏检（invisible_text tile=0.897 / hot_image 0.857 / name_empty 0.895）都是**贴着 0.85 阈值的近失**，
> 阈值升到 0.90 即把 hot_image/invisible_text 救回（多通道召回 →90%，仍 0 假阳，见扫描表）；
> blocking_loop（tile=1.0）是**真·维度盲区**（见局限 §4.2）。

## 4. 诚实的局限（主动写在前面，别等红队戳）

1. **RCA top-1（60%）低于多数类基线（70%）**：因 7/10 故障是 visual，"永远猜 visual"就有 70%。
   我们的价值在**条件准确率（检出即 100% 对）**与**多维度区分**，不是"裸 top-1 比蒙高"。要超过多数类需先把检测召回提上去。
2. **性能维度零侵入抓不到**（blocking_loop 漏，SSIM=1.0）：1.4s 主线程阻塞在"截图前已渲染完"，
   零侵入 time-to-content 计时噪声盖过它。**性能维度需运行时性能钩子**（带 instrumentation 的微信 driver 有 `perf_data` 能抓）。
3. **无 token 的数据故障难抓/难归类**（name_empty 漏）：名称空了像素改动小、又无 `NaN/undefined` token 供 WeBug-R3 命中。
   **只有产生异常 token 的数据 bug 能稳定归到 functional**。
4. **样本规模小**（单 app、单页、N=10、healthy=3）：点估计，未做显著性。论文级需每类 ≥10、扩 3–5 app、bootstrap CI。
5. **跨端 ≠ 跨框架原生**：H5 渲染替代真机；只声称"跨 uni-app + H5"，原生 WXML 另做抽检（§6）。
6. **阈值乐观风险**：0.95 的 90% 召回建立在 H5 健康重渲染确定性(=1.0)上；真实非确定性 app 需自校准，别直接搬。

**维度覆盖真相表**（项目最该讲清楚的一张图）：

| 维度 | 零侵入 H5 路径 | 带 instrumentation 的微信 driver 路径 |
|---|---|---|
| visual 渲染/布局 | ✅ 强（分块 SSIM，阈值 0.90 召回 80%） | ✅ |
| functional 数据(有 token) | ✅（WeBug-R3 抓 NaN/undefined） | ✅ |
| functional 数据(无 token，空绑定) | ⚠️ 弱（像素改动小，易漏/误判） | ✅（业务断言 visible/expected） |
| performance | ❌（零侵入计时噪声） | ✅（perf_data 延迟/内存告警） |

## 5. 顺带发现并修掉的真 bug（25+ agent 对抗式 code review）

确认的真缺陷里，**本轮已修**（回归 `diagnosis/tests/run_all.py` **76/76 全过**）：

| 严重度 | 文件 | 问题 | 修复 |
|---|---|---|---|
| **high** | `mitrix/engine.py` | `compute_metrics` 把"从未执行成功"的用例当假负 → 压低 recall/F1 | 跳过 `success=False` 用例 |
| medium | `diagnosis/diagnose/triage.py` | `card_is_blur` 缺高清晰度护栏 → 真实清晰页（纯色占位卡片）误报 RenderBug | 加 `and blur_full<EDGE_BLUR_GUARD` 护栏 |
| medium | `cascade_oracle.py`（同根因） | full 清晰但 card 模糊时 `confident_pass` 与 `is_blur=True` 自相矛盾、跳过 MLLM | 由上面 card 护栏一并消除 |
| medium | `learned_triage.py` | learned 路径调用功能断言丢了 `ocr_text` → OCR 期望文本校验静默失效 | 补传 `visual["ocr_text"]` |
| low | `triage.py` | 极小图(h≤1)切出空 ROI → cv2.cvtColor 崩 | 空 ROI 退化为整图 |

**额外的 H5 真增益**：零侵入路径能拿 DOM `scrollWidth`，把 WeBug-R2 在真实满幅页的假阳从 True 修成 False
（微信纯截图路径拿不到 DOM，这是 H5 基质的独有优势）。

未修（记入 backlog，详见 `tasks/ws3757h2g.output`）：`layout.py` overlap 用颜色直方图相似度（语义存疑）、
`interaction.py` 跨页污染条件概率 / MIN_SAMPLES=1 统计无意义 / amplification 结果被丢弃、
`app.py` 畸形 JSON 未捕获 500、`qwen_vl_openai.py` 非数值 confidence 抛 ValueError、`/api/feed` 缺分页边界。

## 6. 用户选的"WeChat 原生 WXML 抽检"（需人工开发者工具，待执行）

H5 是主量化证据；原生 WXML 抽检证明"真目标平台也成立"。原生 WXML 无法 headless 渲染（需微信运行时），
需**用户手动开微信开发者工具**（历史教训：只有人工开的 cold session 能稳定截图）：
1. 在 `third-wxapp-mall`（已在本地）对 1–2 页做同类源码变异（缺图/布局/数据）。
2. 用户开发者工具打开该项目；connect 模式截图。
3. 跑同一诊断管线，核对维度判定。
（脚手架可在用户就绪时补；当前不阻塞主结论。）

## 7. 复现

```bash
# 1) 起静态站（已编译好的 xtx H5；若无则先 cd fault_bench/xtx && npm run build:h5）
cd fault_bench/xtx/dist/build/h5 && python -m http.server 8099 --bind 127.0.0.1 &
# 2) 跑基准（git clean→逐变异 build→headless 渲染→诊断→打分→出报告）
cd D:/weixinmp_test
PYTHONUTF8=1 VT_MLLM=heuristic python fault_bench/bench/run_bench.py --url http://127.0.0.1:8099
# 3) 阈值扫描（不重跑）
PYTHONUTF8=1 python fault_bench/bench/sweep.py
# 报告在 fault_bench/bench_out/bench_report_<ts>.{md,json}
```

环境：node v22 / pnpm 10 / Python(anaconda) + playwright+chromium + cv2/PIL/skimage；
Qwen key 在 `qwen.md`（DashScope OpenAI 兼容端点，已验证）。

## 8. 对外可站住的 claim（粘进答辩/论文 —— 已按真实数字校准）

- *"在真实第三方 uni-app 上，崩溃测试漏检 100% 的注入视觉/布局/数据故障；Vision-Triage 仅凭截图+DOM 零侵入
  在 0 假阳下检出 60%（阈值放宽至 0.90 多通道达 90%、仍 0 假阳），且**检出即 100% 指对根因维度**（6/6）。"*
- *"Owl Eyes/Nighthawk **检测** UI 问题、Trident 用自由文本**描述**；我们更进一步**分诊**到可执行维度
  （渲染/布局/数据/性能）——把 yes/no 检测器变成告诉开发者『该查哪个子系统』的路由器。"*
- *"把视觉回归从整图 SSIM 升级为分块 SSIM，同阈值（0.85）召回 30%→50%、放宽阈值（0.90）多通道 →90%，
  证明真实内容密集页上检测粒度才是瓶颈，而非检测器种类。"*
- *（诚实附注）"裸 RCA top-1（60%）尚低于多数类基线（70%），瓶颈在检测召回；提召回是首要 backlog。"*

---
*关联：[`EVALUATION_PROTOCOL.md`](EVALUATION_PROTOCOL.md)（有效性方法学）、记忆 [[project-h5-mutation-bench]]、[[project-novelty-positioning]]、[[project-prior-work-threats]]。*
