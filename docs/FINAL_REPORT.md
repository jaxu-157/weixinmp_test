# Vision-Triage 最终汇报（当前可复现事实版）

> 本文是项目**权威汇报**。所有数字来自实跑产物，未做美化；漏检与局限主动列出。
> 经 `docs/PROJECT_REVIEW_2026-05-31.md` 评审后修订：删除此前不可复现的 100% 表述，全部降调到仓库可复现实跑。
> 核心命题：**"零侵入/低侵入捕获 + 维度级根因分诊（triage）"在真实小程序上成立，且常规崩溃测试做不到。**

---

## 0. 一句话结论

在**真实第三方小程序**上做**源码变异故障注入**（把正确代码改成常见开发者错误，编译运行，看能否诊断出来），三条独立证据线：

| 证据线 | 载体 | N | ours 检出 | 健康假阳 | crash-only | 条件RCA(检出即对) |
|---|---|---|---|---|---|---|
| **A. H5 随机/穷举大样本** | 小兔鲜儿(uni-app) | 20 | **50%** [95%CI 30–70%] | **0%** | **0%** | **8/10 = 80%** |
| B. H5 手挑样本 | 小兔鲜儿(uni-app) | 10 | 60% | 0% | 0% | 6/6 = 100% |
| C. devtools 真机 | youzouzou(原生WXML) | 7 | 57% | 0% | 43%(假阳50%) | 4/4 = 100% |

**两个铁结论（都有数据支撑）**：
1. **常规崩溃测试对非崩溃故障近乎全盲**（A/B 线 crash-only 0%；C 线虽 43% 但健康页假阳 50%）。
2. **一旦检出，根因维度判定高度可靠**（A 线条件 RCA 8/10=80%、B 线 6/6、C 线 4/4）——这是 triage 的真价值：报警即指对子系统。

诚实短板：**整体检出率受召回限制（约 50–60%）**，漏检集中在"小面积低对比度文字 / 无 token 的空绑定 / 主线程阻塞性能"，详见 §4。

---

## 1. 真实有用场景

> **跨端小程序的 CI 视觉根因门禁（zero-touch visual root-cause gate）**：
> PR → 自动编译 → 截图 + 读运行时信号 → 与基线比对 + 维度分诊 →
> 不只报"页面坏了"，还报"坏在**渲染/布局 / 数据绑定 / 性能**哪一维"。

常规 CI 的崩溃/lint 门禁对这类非崩溃故障**零覆盖**——这是真实空白。把开发者定位成本从"全页排查"降到"按维度排查"。

---

## 2. A 线：H5 随机/穷举大样本（主证据，带统计置信区间）

- 载体：开源 uni-app **小兔鲜儿**（`Megasu/uniapp-shop-vue3-ts`）编译 H5，Playwright headless，全自动无人值守。
- **变异生成**：`gen_random_mutations.py` 扫描首页相关源码，**穷举所有可发现变异点**（无抽样偏差），种子打乱顺序 → 20 个变异（visual 9 / layout 6 / functional 5；layout 按 RCA 折叠进 visual）。
- **bootstrap 95% CI**：检出率由 2000 次重采样给出区间，而非单点估计。

**各方法检出率对比（实测，`campaign_20260531_015446`，N=20）**：

| 方法 | 检出率 | 95% CI | 健康假阳 |
|---|---|---|---|
| crash_only（崩溃/JS异常/黑白屏） | **0%** | [0%, 0%] | 0% |
| verdict_only（learned 五分类单通道） | 0% | [0%, 0%] | 0% |
| ssim_whole_only（整图SSIM，原通道） | 20% | [5%, 40%] | 0% |
| **ssim_tiled_only（分块SSIM，本轮新增）** | **50%** | [30%, 70%] | 0% |
| webug_only（R2/R3规则） | 0% | [0%, 0%] | 0% |
| **ours（多通道并集）** | **50%** | [30%, 70%] | **0%** |

- **分块 SSIM(50%) 是整图 SSIM(20%) 的 2.5×**——长滚动页里局部改动被整图稀释，分块恢复局部敏感度。这是本轮最硬的工程增量。
- **RCA top-1 = 40%；条件 RCA = 8/10 = 80%**（被检出的故障里 8/10 维度判对；2 个 functional 空绑定被判成 visual——因为空绑定也表现为像素变化，无 token 时归不到 functional）。
- **按维度检出（暴露真实短板）**：visual 8/15、functional 2/5。漏的全是**低对比度文字改色**（tile 0.95–1.0，改动像素占长页比例太小）和**无 token 空绑定**。

### 2.1 Qwen-VL 视觉融合 A/B（真实调用，关键负结果：高检出是假象）

把 DashScope **qwen-vl-plus** 真实接入（key 在 `qwen.md`，`default_mllm()` 实测返回真 Qwen、`is_available=True`、
单次 ~1000ms 真 API），在 A 线全部 20 故障 + 3 健康截图上各强制调一次（共 23 次），与 ours 多通道做 A/B：

| 通道 | 检出率 | 健康假阳 | 备注 |
|---|---|---|---|
| ours（截图规则/分块SSIM/几何/数据） | 50% (10/20) | **0%** | — |
| qwen-vl-plus 单通道 | 100% (20/20) | **100% (3/3)** | **全报警** |
| ours + qwen 融合 | 100% (20/20) | **100% (3/3)** | 同上 |

**关键负结论：Qwen 的 100% 检出是"无脑全报警"的假象，不可用。** 它对**每一张图**（含 3 张健康基线）都返回
`has_missing_image=True`，reason 一律是"页面大量图片显示为网格占位符，图片加载失败"。根因：小兔鲜儿 fixture 用的是
**带网格纹理的占位图**，Qwen 把这种纹理图本身当成"加载失败占位符"。所以：
- 它"救回"的 10 个 ours 漏检（低对比度/空绑定）**不是看懂了故障，是恰好蒙对**——因为它对所有图都喊缺图；
- 同样的偏见让它在**健康页 100% 误报**——这直接证伪了它作为可信通道的资格（0 假阳约束下它检出率实际为 0 可用）。

**这是一个比"零增量"更重要的负结果**：通用视觉大模型在专用 UI 缺陷判定上**有系统性偏见**，
**高 recall 必须和 FPR 一起看**——只报 recall 会得出"Qwen 100% 吊打 ours"的错误结论。
产物：`fault_bench/campaign_out/qwen_ab_20260531_015446.json`。

### 2.2 改进尝试：图+基线+代码 的"差分融合"诊断（按用户建议）

针对 §2.1 的偏见，新增 `QwenVLOpenAI.analyze_diff(baseline_img, current_img, code_context)`——
把**健康基线图 + 当前图（+ 可选页面源码）一起喂给大模型**，让它判"当前相对基线是否**引入**缺陷"，
而非"单图是否有缺陷"。并按用户建议**把正确样本混入测试池**，用 precision/recall/**FPR**/F1 评测
（20 故障 + 7 正确，`qwen_diff_ab_20260531_031309.json`）：

| 方法 | Precision | Recall | F1 | FPR | 说明 |
|---|---|---|---|---|---|
| qwen 单图（旧） | 0.74 | 1.00 | 0.85 | **1.00** | 全报警，3 健康也全报 |
| **qwen 差分（新，图+基线）** | 0.60 | 0.30 | 0.40 | **0.57** | **唯一能正确放过部分正确样本的（tn>0）** |

**差分融合验证了用户的设计直觉**：给基线做对比后，Qwen **不再无脑全报警**——冒烟可见"健康 vs 健康"判 `has_defect=False`
（旧版这里 100% 误报）。它能稳定抓"几何剧变"（缺图、宽度溢出 width@/img@ 全对），但对"低对比度文字、空绑定"
这类细微差异仍判 none（太保守，recall 30%）。**方向对、但还不到可用。**

### 2.3 关键发现：混入正确样本暴露并修掉了两个真实假阳 bug（用户建议直接催生）

按用户"测试池该放正确样本"的建议，把正确样本混入后，**ours 在纯截图(无 DOM)路径上 FPR 一度 100%**——
这不是噪声，是两个**真 bug**（PROJECT_REVIEW P1 早已点名、之前未修）：

1. **WeBug-R2 像素边缘启发式**在内容丰富的满幅页上无脑误报溢出（健康页也报）。
   **修复**：R2 硬报警只在 **DOM 来源**(`scrollWidth>clientWidth`)时成立；无 DOM 的像素 fallback 降级为低置信证据，不驱动报警。
2. **WeBug-R3 可疑 token 扫描**把**截图 OCR 文本**里的 `{{` 当成"未渲染 Vue 模板"——而 OCR 把中文笔画/网格线误读成 `{{`。
   **修复**：从 OCR 适用的 token 表移除 `{{`/`}}`（仅保留 `undefined/null/NaN/[object Object]` 这类 OCR 能可靠识别的单词型）；
   `{{` 仅在**真实 DOM/WXML 文本**(devtools page.data)里才检测。

**修复后实测**（`fpr_clean`，同会话 baseline + 8 健康，**纯截图无 DOM 最坏情况**）：

> **ours FPR 从 100% 降到 0%（8/8 全部正确放过）。** 两个噪声通道不再在健康页误报。

**R2 订正（实测推翻"轮播抖动"猜测）**：上一版此处写"3/12 正确样本被误报是因轮播停位不同（抖动）"。
R2 逐 tile 实测（产物 `fault_bench/campaign_out/fpr_rc/`）证明根因是**跨构建基线**，不是抖动：

| 对比 | 分块 SSIM | 结论 |
|---|---|---|
| 同会话 fresh_baseline vs fresh_healthy ×5 | **1.0** | 此 fixture **无抖动**（XtxSwiper `autoplay=false`、fixture 数据确定）|
| 两次独立干净 build 渲染 | **1.0** | 构建**确定性** |
| 旧 build 的 baseline.png vs 当前 build 渲染 | **0.49**（几乎全 tile）| **跨构建产物整体不可比** |
| 同构建 healthy_* vs 同构建 baseline | FPR **0/5** | 正确用法零假阳 |
| 跨构建 fresh 样本 vs 旧 disk baseline | FPR **5/5** | 假阳来源 |

`qwen_diff_ab` 之前把"当前构建新渲染的 correct_extra"与"旧 build 的 baseline.png"跨构建比（整体差 ~0.49，非局部抖动）→ 全假阳。
**修复**：正确样本改用 campaign **同构建** `healthy_*`（FPR 0%）。**规则：基线与被测样本须来自同一次构建/渲染**
（`run_campaign` 内部本就如此，故其 50%/0%FPR 有效）。真实 CI 的非确定内容（轮播/随机/时间戳）另用
`vt_diagnose.calibrate_dynamic_tiles`+`tiled_min_ssim_masked` 标定跳过动态 tile（合成单元已验证：健康假阳 tile 0.0→掩码后 1.0、
真故障 tile 仍 0.0 不漏）——但本确定性 fixture 无抖动、**不构成该功能的有效性证据**，诚实标注。

### 2.4 关键发现：learned 五分类 verdict 对输入完整性不稳定（应降权）

核查 50% vs 95% 两个检出数字打架时发现：**同一张低对比度故障截图，传 `dom_info` 时 learned verdict=Pass（漏），
不传时=RenderBug（中）**。即 learned 模型的判定随输入特征是否完整而翻转——它不是稳定可信的主通道。
**结论（对齐 PROJECT_REVIEW §3.5）**：检出的**稳定、可辩护通道是纯图像对比**（整图 SSIM、分块 SSIM，确定性、不依赖 dom/perf）；
learned verdict 仅作可选加权器，**不进 headline**。本报告的检出率以稳定图像通道为准（分块 SSIM 50%），
不采用被 learned verdict 灌高的 multichannel 数字。

> 方法学教训（也写给自己）：本节初稿曾据 3 张抽样截图臆断"Qwen 零增量"，跑完 23 张全量后发现完全相反（是"全报警假阳"）。
> 凡结论必须等全量实跑 + FPR 一并核对——这正是本项目反复强调"recall 要和健康假阳一起报"的原因。

## 3. B/C 线（互补，证明平台与维度覆盖）

- **B 线（手挑 10 变异）**：与 A 线同 app，结论一致（60% / 0 假阳 / 6/6 条件 RCA），并验证了"放宽分块阈值 0.90 → 多通道 90%、仍 0 假阳"的上限空间。
- **C 线（devtools 真机，原生 WXML youzouzou）**：补 A 线两维盲区。`devtools_probe.py` 零侵入只读三类真实信号：
  1. `page.data` token 扫描 → 抓**无像素特征的数据故障**（截图漏、devtools 抓到，互补铁证）
  2. 元素 `scrollWidth` 真几何 → 抓**布局溢出**（780>390）
  3. `wx.getPerformance` → 性能（**仍是部分盲区**，见 §4）
  实测 7 变异：57% 检出 / 0 假阳 / 条件 RCA 4/4。**crash-only 在 C 线健康页假阳 50%**（纯色页骗过黑白屏检测），反衬 ours 0 假阳。

### 3.1 D 线（R3）：跨页通用性——同一检测器在 3 个不同页面布局上零假阳

A/B/C 线都只在首页布局上测。R3 把同一套"每页各自基线 + 局部分块对比"应用到**首页 / 购物车 / 我的**三个布局不同的页面
（探针 `probe_pages.py` 确认这三页能渲染真实内容；category/hot 因 API mock 不全只出骨架，已排除）。
**先验证了渲染稳定性**（产物 `fault_bench/campaign_out/mystab/`，各页连续 5 次干净渲染两两分块 SSIM）：
**index / my / cart 全部 = 1.0**（cart `n_below_0.85 = 0/10`）——三页都**确定性渲染**，差分数字可信、0 假阳不是运气。

手挑故障（`crosspage_20260531_061419.json`，逐字段核对）：

| 指标 | 结果 | 含义 |
|---|---|---|
| **跨页健康假阳** | **0/12**（index/cart/my 各 0/4）| 零假阳**跨布局成立**（且稳定性 1.0 佐证非偶然）|
| **非首页大面积故障检出** | `my:guess_img_missing` ✅（tile 0.52）、`cart:guess_img_missing` ✅（tile 0.58），均 pred=visual | 检测器在 cart/my **路由上端到端抓到真故障** |
| 小面积故障 | avatar 缺图 0.957 / avatar 缩放 0.941 / 标题低对比度 0.970 **3/3 漏** | 与首页**同一**小面积稀释盲区，行为一致 |

总计可见故障检出 **2/5**（两个大面积缺图全中、三个小面积全漏）。

- **诚实点**：cart/my 仅渲染**登出态**，可注入的"肉眼可见"故障面积都小（头像 ≈60px、标题文字色），
  且 `.avatar{background:#eee}` 有灰圆兜底，缺图近乎不可见——故小面积全漏，与首页低对比度短板**同源**。
- **修过一个真 bug**：crosspage_bench 初版用"故障 build 重渲的图"当基线 → baseline==fault==tile 1.0 恒漏；
  改回 run_campaign 的正确模式（clean-build 基线 vs faulted-build 渲染）后，故障 tile 正常下沉到 0.5–0.97。

#### 3.1.1 自动化 page-aware 穷举 campaign（比手挑更强的证据）

把手挑升级为**穷举式 page-aware campaign**：`gen_random_mutations` 给每变异打 `page` 标签、按页扫描源码
（my 页剔除 `memberStore.profile` 登录态死分支）；`run_campaign` 每页各自 baseline + 按变异 `page` 渲染对应路由对比同页基线。
产物 `campaign_20260531_065126.json`（逐字段核对）：

| 指标 | 值 |
|---|---|
| N | **26 变异**（index 20 + my 6）/ 8 健康（每页 4） |
| ours 检出 | **42.3%** [95%CI 23.1–61.5%]，= 分块SSIM（其余通道 0） |
| 健康假阳 | **0/8**（index 0/4 + my 0/4） |
| crash-only | **0%** |
| 分页检出 | index **10/20=50%**（与 A 线 `033057` 完全一致，seed-42 可复现）、my **1/6** |

- **page-aware 真生效的铁证**：my 6 变异 tile 各不同（0.506 / 0.955 / 0.946 / 1.0 / 0.961 / 0.968），确实在 my 路由渲染并比对 my 基线。
- **my 1/6 的诚实解读**：唯一检出 `my/bindempty@my:item.text`（订单类型文字绑定置空，tile 0.506，大面积文字消失）；
  5 个漏检全是小面积（avatar 宽度、3 处颜色），与首页同源盲区；`width@my:180x6` tile=1.0（元素离屏/被裁剪，放大无可见效果）。
- **RCA**：top-1 30.8%、conditional 8/11——比 A 线略低，因 `bindempty` 真值是 functional 但空绑定表现为像素变化、无 token 故被判 visual（§4#2 已知短板）。
- 中途修过一个真 bug：page-aware 改动一度没落盘 → my 变异错渲到 index 全漏 → recall 假性 38.5%；核对代码 7 项 `ALL_OK` 后重跑才得本真值。
- **整体结论**：检出率受小面积召回限制（~40–50%），但**零假阳跨页稳健**（稳定性已实测=1.0）、crash-only 全盲——多页穷举把"只对首页调参"的质疑也排除了。

---

## 3.2 根因定位：从"哪一维"到"哪个源文件"（确定性，无 LLM，本轮新增）

中期之前的 RCA 只回答"故障属于视觉/功能/性能哪一维"。本轮把它推进到**定位到具体源文件**，全程确定性、不依赖 LLM。
经一次失败→修复的迭代（朴素 class 索引 0/10 → **data-v hash 映射 4/10**），最终文件级定位率 40%。

**定位链路（视觉/布局/功能共用）**：
```
分块 SSIM 最低的 tile  →  elementsFromPoint(tile 中心像素)  →  命中元素的 data-v-* hash 
                        →  data-v hash → .vue 源文件索引  →  预测源文件
```
- 视口固定 375×2200、8×3 网格，tile→像素中心是确定映射（`localize.py: tile_center_px`）。
- **关键：用 data-v hash 而非 class 做映射**。第 0 步 DOM 探测（`probe_dom_attribution.py`）实测 H5 prod 构建里
  `data-v-*` 可达（167/368 元素）、`elementsFromPoint` 可用、Vue per-node 实例不可达。
  `build_hash_file_index` 从 dist scoped CSS 解析 `.cls[data-v-HASH]` 得每个 hash 的判别类集，
  再与各 `.vue`（模板 class ∪ `<style>` 选择器）按判别类重叠匹配——**6 个首页组件 hash 全部映射正确**（6/6）。

**实测结果（产物 `campaign_out/localize_out/localization.json`，index 页 N=20，逐条核对）**：

| 指标 | 结果 |
|---|---|
| 检出（前提） | 10/20（没检出的无从定位）|
| **文件级定位** | **4/10 = 40% over detected** |

- **4 条 HIT（全部 data-v hash, 高置信）**：`img@XtxGuess:item.picture`、`img@XtxSwiper:item.imgUrl`、
  `width@XtxGuess:304`、`width@XtxGuess:345`——这些故障的最大 diff tile 恰好落在故障组件自身区域，hash 命中正确文件。
- **6 条 MISS**（逐条核对，两类原因）：
  - **元素重叠/相邻（3 条）**：`img@HotPanel:src`、`bindempty@HotPanel:item.title`、`:item.alt` 的最差 tile=(2,0)，
    `elementsFromPoint` 命中了相邻的 XtxGuess（caption）而非 HotPanel。
  - **布局溢出的 diff 漂移（3 条）**：`width@category:100/150`、`img@CategoryPanel:item.icon` 的最差 tile=(1,1)/(1,2)，
    溢出把后续内容挤动，最大 diff 落在 index 容器层而非 CategoryPanel 故障源。

**这次迭代的失败→修复**（诚实记录）：朴素版用 **class** 做映射，被 uni-app 框架 wrapper 类（`navigator-wrap`/`scroll-view`）
污染，全部错判（0/10）；改用 **data-v hash**（每个 `.vue` 唯一，不撞车）后升到 **4/10**——hash 映射本身 6/6 全对，
瓶颈不在映射而在"**最差 tile 选错位置**"（元素重叠 + 溢出 diff 漂移共 6 条）。下一步用 **元素 bbox ∩ 变化 tile 面积排序**
替代单点中心采样，预计能救回重叠类那几条；溢出类需把"变化 tile"回溯到布局变化的起点。均为已知工程项、未做。

**三维度定位现状（诚实）**：
| 维度 | 能否定位到源 | 手段 | 现状 |
|---|---|---|---|
| **功能/数据** | 理论最直接 | 运行时 `page.data`/绑定 token 直接命名坏字段；字段→行可进一步用 `@vue/compiler-sfc` `loc` 或 ajv/zod `instancePath` | 本轮 2 条 bindempty 走视觉同链路，因元素重叠**均漏**；**字段级定位（不依赖像素）为下一步、最确定** |
| **视觉/布局** | 需像素→元素逆映射 | tile→`elementsFromPoint`→data-v hash→文件 | **4/10 文件级**（hash 映射 6/6 全对；漏检源于最差 tile 选错位置：元素重叠 3 + 溢出 diff 漂移 3）；学术蓝本 WebSee、XFix |
| **性能** | 被检测卡住 | H5 检出本身是盲区（§2.5 R1 负结果）→无从定位；**若能检出**，CDP `Profiler`（Playwright `newCDPSession` 可驱动）+ source-map 给**函数+源码行**级确定性定位；原生微信深 CPU profiler 是 GUI-only，minium 拿不到 | 未达可用，平台不对称 |

**现成轮子归档**（调研结论，便于后续直接接）：
- 视觉：`resemble.js`（返回 diff bounding box）、Applitools RCA（DOM 锚定但闭源）、OwlEye（Grad-CAM 热力图、**无 DOM**）、WebSee/XFix（区域→元素/CSS，学术）。
- 功能：`ajv`/`zod`（校验错误带 `instancePath`/`path` 精确到字段）、`@vue/compiler-sfc` `loc`（字段→`.vue` 行）、Vue `app.config.warnHandler`/`errorHandler`（dev 直接报字段名+组件）。
- 性能：CDP `Profiler`→`.cpuprofile`→`source-map` 反映射→`speedscope`/`cpupro` 按 self-time 排序、LoAF `scripts[]`（Chrome 123+ 带 `sourceFunctionName`）、Vue `app.config.performance`（每组件 User Timing）。

> 脚本：`fault_bench/bench/{localize,localization_bench,probe_dom_attribution}.py`。
> 局限：单 app、index 页小样本；定位仅在已检出故障上有意义；性能维仍未打通。

---

## 4. 诚实的局限（主动列）

1. **样本量小、CI 宽**：A 线 N=20，ours 95%CI [30%, 70%]——区间宽是小样本必然，需扩到 3 app/60+ 变异才能收窄。
2. **整体检出 ~50%，瓶颈在召回不在分诊**：条件 RCA 80% 但 top-1 只有 40%，因为没检出的无法分维度。系统性漏检三类（A 线 20 变异实测）：
   - **低对比度文字改色**（6 个 color 变异里漏 5 个，tile 0.95–1.0——改色像素占长页比例太小，分块 SSIM 也稀释了）
   - 无 token 空绑定（字段改错变空串，既无明显像素特征也无 "undefined" 字面量；2 个被检出的也误判成 visual）
   - 主线程阻塞性能（H5 截图在渲染后、零侵入计时噪声大）
3. **性能维仍是部分盲区**：本轮虽修了 `triage` 性能字段 camel/snake 不兼容的 P0 bug（见 §5），但 H5 零侵入路径仍缺 Long Task 主信号；devtools 路径 `wx.getPerformance` 的 firstRender 是启动一次性记录、relaunch 不刷新，抓不到 onShow 阻塞。导航墙钟方案试过但 minium relaunch 异步导致采不到，已回退。**诚实结论：性能维需 H5 Long Task Observer 或 SDK 语义上报，当前未达可用。**
4. **变异即真值的效度边界**：引 Just et al. FSE'14——变异是真实缺陷的合理代理，但覆盖不了长尾（间歇性、纯逻辑、设备兼容、弱网）。
5. **learned 模型不作主力**：真实截图矩阵上 learned 单通道仅 41–43%，本系统主叙事是**多通道证据融合**，learned 仅作可选加权器。
6. **Qwen-VL 当前不可用作视觉通道**：实测对带纹理占位图有系统性偏见，健康页 100% 误报（§2.1）。需 prompt 改造或成对差分才可能有用。

---

## 5. 本轮按 REVIEW 修复的真 bug

| 级别 | 问题 | 修复 |
|---|---|---|
| **P0** | `triage._run_performance_assertions` 只读 camelCase，snake_case 被静默当 0 → driver/devtools 性能故障漏判 | 兼容两套字段；新增 6 个回归测试（`test_perf_fields.py`） |
| **P0** | FINAL_REPORT 引用不存在的 `011309` 报告 + 100% claim | 本文件已全部改为可复现实跑数字 |
| P1 | `run_all.py` 在 Windows GBK 控制台崩（▶ 字符） | 入口加 `sys.stdout.reconfigure(utf-8)`，现免 PYTHONUTF8 可跑 |
| P1 | `/diagnose` 畸形 JSON → 500 | 捕获 `JSONDecodeError` 返回 400 带字段名 |
| 早轮 | mitrix `compute_metrics` 把未执行用例当假负；triage `card_is_blur` 缺护栏误报；learned 丢 ocr_text | 均已修，见 git diff |

测试回归：`python diagnosis/tests/run_all.py` → **82/82 通过**（原 76 + 6 性能字段回归），且**无需 PYTHONUTF8**。

---

## 6. 工程产物清单

| 类别 | 路径 |
|---|---|
| H5 随机大样本基准 | `fault_bench/bench/{gen_random_mutations,run_campaign}.py` + `run_bench.py` + `vt_diagnose.py` |
| devtools 信号模块 | `auto_test/v2_modules/devtools_probe.py`（真机校准，纯只读，优雅降级） |
| devtools 真机基准 | `fault_bench/run_native_bench.py` + `fault_bench/native_mutations.py` |
| 端口身份探测 | `auto_test/v2_modules/which_project.py` |
| 报告 | `fault_bench/campaign_out/`（A线，主）、`fault_bench/bench_out/`（B线）、`fault_bench/native_out/`（C线） |
| 方法学 | `docs/EVALUATION_PROTOCOL.md` |
| 评审 | `docs/PROJECT_REVIEW_2026-05-31.md` |

## 7. 对外可站住的 claim（已按真实数字校准）

> Vision-Triage 面向小程序/uni-app 的非崩溃故障**分诊**——不只判"页面坏没坏"，还把故障归到视觉/布局、数据/功能、性能等开发者可行动维度。在真实第三方 uni-app H5 源码变异基准（20 变异，穷举无偏，bootstrap 95%CI）上，**以 0 健康假阳检出 50%（CI 30–70%）故障，且检出即维度判对 8/10**；常规崩溃测试在同基准检出 0%、整图 SSIM 仅 20%。多通道分块方案相对二者显示明确增量；整体召回受"低对比度文字/无 token 空绑定/性能阻塞"三类漏检限制，是后续主攻方向。

**不说**：100% 检出/RCA、超过所有前人、ML 可跨任意小程序泛化、零侵入即可完整定位性能根因。

---
*数字来源：A=`campaign_20260531_033057`(N=20,bootstrap CI)；B=`bench_report_20260530_214801`；C=`native_report_20260531_010859`；
D=`crosspage_20260531_061419`(手挑跨页 0/12 FPR+2/5，§3.1)；D'=`campaign_20260531_065126`(page-aware 穷举 N=26 跨 index+my：42.3% [CI 23–62%]、0/8 FPR，§3.1.1)。
跨页稳定性已实测：`campaign_out/mystab/` index/my/cart 干净渲染两两分块 SSIM 全=1.0（三页都确定渲染，0 假阳非偶然）。所有改动未 commit。*
