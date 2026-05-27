# /goal 自主循环进度台账

> 由 `/goal` 命令维护。每轮：做了什么 / 证据在哪 / 还差什么。
> 北极星：**工程可用 AND 研究可辩护**，双标准全绿才停（见 `.claude/commands/goal.md` §6）。

## DONE 双标准（核验状态）

**A. 工程可用**
- [x] Qwen-VL 经 OpenAI 兼容端点真正接入 cascade，参与 learned-triage 融合 — **Round 1 完成**
- [x] 规则 vs Qwen cascade vs qwen_always 的准确率/成本/延迟消融表 — **Round 2 完成**（歧义带上 cascade 用 1/4 成本达到 qwen_always 同等准确率）
- [~] ≥3 个独立真实/开源小程序跑通 — **Round 5 部分**：demo/foreign(uni-app) + **wxapp-mall(原生, 跨框架 attach 100%)** 跑通；
  tdesign build+attach 成功但截图被 devtools flaky 卡住（需用户手动重开 devtools 重跑）。
  关键发现：真实健康 app 上开箱判定通道假阳高（verdict 50%/webug 75%），仅 baseline 0% 泛化 → 需按真实基线校准。
- [ ] §9 复现指南能从干净环境一把跑通

**B. 研究可辩护**
- [x] 差异化句式每条有 delta + 引用支撑 — **Round 3 完成**（§7.1/7.2，4 篇论文核实定位）
- [~] §5 红队所有问题有答案或被实验消解 — **Round 3 跑了一轮**（`docs/红队答辩.md`）；4 个"还需补"项进 backlog
- [x] 每条对外 claim 过"一句话 delta"测试；虚的已砍 — **Round 3 完成**（"必须降级"清单已修订 claim）
- [x] 对现有 contribution 给出诚实价值边界 — **Round 3 完成**（cost-accuracy 价值 + 明确不 claim "更准"）

---

## Backlog（活的，按 ROI 排序）

- **P0** [需人类] 在第 3 个小程序上验证零侵入接入。**优先原生 WXML**（把 claim 从"跨 uni-app"升级为"跨框架"）。
  候选已用 GitHub API 核实结构/数据源（2026-05-26 Round 3+）：

  | 候选 | star | 框架 | 数据源 | 评估 |
  |---|---|---|---|---|
  | **Tencent/tdesign-miniprogram-starter-retail** | 818 | 原生 JS+WXSS | **mock(useMock:true)** + CDN图 | ★**首选**：9页真实零售app(home/category/goods/cart/order/...)，开箱即跑无需后端，官方维护(2026-05)，证跨框架 |
  | **lin-xin/wxapp-mall** | 1.7k | 原生 | 静态/内置(app.js空,无http) | ★备选：极轻量自包含，开箱跑；偏老(2019)但原生语法稳定 |
  | wechat-miniprogram/miniprogram-demo | 7.2k | 原生 | 组件/API/云开发示例 | 保底：一定能编译跑，但是组件画廊、profile(feed/counter/layout)映射别扭 |
  | dmego/together | 264 | 原生 | 疑云开发(有logs页) | 中：需配云环境 |
  | EastWorld/wechat-app-mall | 21.6k | 原生 | **需自建后端**(config.js指API host) | 重：最火但要起服务器 |
  | Tencent/westore | 4.3k | 框架monorepo | 例子在 packages 子目录 | 跳过：根目录非可跑app |
  | lypeer/wechat-weapp-gank | 744 | 原生 | 公开Gank API | 跳过：API 2016 起疑似失效 |

  推荐路线：先 **tdesign-retail**（真实+开箱+跨框架）跑零侵入 driver + 24-case 矩阵；如要更轻量对照再加 **wxapp-mall**。
  *需先启动微信开发者工具*（见 §4）→ 等用户。
- **P0** [红队 Q3] 更大/更真实（非合成）歧义样本集 + 人工标注"可感知模糊"基准，给 Qwen vs rule 错误分布可信结论。
- **P1** [红队 Q2] learned vs rule 显著性检验（McNemar / bootstrap CI），目前只报点估计、不能声称"显著优于"。
- **P1** [红队 Q1/Q6] 与 Trident / WeDetector 的**同台**对比/互补覆盖量化（目前多为论证级）。
- **P1** 扩大歧义带测试集：当前仅 1 张基底 × 8 模糊核（proof-of-concept）。补多基底 + 多退化类型
  （运动模糊、JPEG 压缩块、局部模糊、褪色），让 cost-accuracy / FP-reduction 结论更稳。
- **P1** Round 2 发现 Qwen 在 k05 边界与合成 GT 不一致：用人工标注或更明确的"可感知模糊"基准
  重新定 GT，给 Qwen vs rule 的错误画像（FP/FN 各自分布）一个更可信的说法。
- **P1** 消融 learned-triage 特征贡献：加/不加 Qwen 特征的 verdict 准确率差，量化"多模态融合必要性"。
- **P1** §7 逐条补"vs WeDetector/WeReplay/MiniScope/Wemint/Owl Eyes/Trident/Uber delta + 证据"。
- **P2** cost-accuracy 帕累托前沿做实（便宜规则兜底 + 贵 Qwen 仅在歧义带）。
- **P2** §9 复现指南固化种子/版本/命令，干净环境验证。

---

## 轮次日志

### Round 1 — Qwen-VL 真正接入融合诊断路径 ✅
**日期**: 2026-05-26

**做了什么**
- 新增 `diagnosis/diagnose/mllm/qwen_vl_openai.py`：走 qwen.md 的 OpenAI 兼容端点
  （`base_url=.../compatible-mode/v1`，`openai` SDK，图像 base64 data-uri，model `qwen-vl-plus`），
  输出结构化 `OracleResult`。key 解析顺序：构造参数 → `DASHSCOPE_API_KEY` → 仓库根 `qwen.md` 首行。
- `mllm/__init__.py` 新增 `default_mllm()` 工厂 + 导出 `QwenVLOpenAI`；`VT_MLLM=heuristic|qwen` 可强制选择。
- `cascade_oracle.py` 默认改用 `default_mllm()`：有 key 用真 Qwen，否则回退 `HeuristicMLLM`。

**证据**
- 连通性：text ping 返回 OK；blur 截图视觉调用返回 `{"has_blur":true,"confidence":0.95}`（正确）。
- 工厂：有 key → `qwen_vl_openai`；`VT_MLLM=heuristic` → `heuristic_mllm_v1`（已验证）。
- 消融（`diagnosis/diagnose/training/reports/cascade_evaluation.json`，14 离线样本）：

  | oracle | visual_acc | verdict_acc | avg_ms | 升级率 |
  |---|---|---|---|---|
  | rule_only | 71.43% | 100.00% | 15.84 | 0% |
  | cascade(→真Qwen) | 71.43% | 100.00% | 692.35 | 57.14% |
  | heuristic_always | 71.43% | 100.00% | 18.80 | 100% |
- 回归：`diagnosis/tests` 76/76 通过，无破坏。

**诚实发现（不许overclaim）**
1. Qwen 已机械接入并真实调用，但在这 14 样本上**对准确率零增量** —— 三种 oracle 端到端 verdict 都 100%
   （learned tree 靠 functional+perf 特征就够），visual 子准确率都 71.43%。
2. **升级带 mis-calibrated**：cascade 把 counter（纯文字/数字页，无图）当"模糊歧义"升级到 Qwen
   （5 个 counter case 全升级，每个 ~1000-1600ms），而真正的 `feed blur_image` 规则法 13ms 自信判对、**没升级**。
   → 57% 升级率几乎全是浪费的开销，Qwen 同意规则结论故无害但无益。
3. 结论：**Qwen 的价值（cost-accuracy 权衡）尚未被现有测试集证明**。这正中红队 Q3（"要你这套 cascade 干嘛"）。

**下一步**（已进 backlog P0）：重新校准升级带（只在视觉不自信时升级）+ 造歧义带测试集（规则错、Qwen 救）。
报告 `docs/结题报告.md` 的正式整合**推迟到 cost-accuracy 价值跑实之后**，避免把中间结论写进 artifact。

### Round 2 — 校准升级带 + 歧义带证明 cascade 的 cost-accuracy 价值 ✅
**日期**: 2026-05-26

**做了什么**
- 校准 `cascade_oracle._is_confident_zone`：升级判定**只看 blur_score，删除 edge_density 作为 pass 门槛**。
  根因：edge_density 是"内容稠密度"代理而非"模糊度"信号——文字稀疏但清晰的 counter 页(blur≈429/edge≈0.023)
  被旧逻辑(blur≥400 AND edge≥0.08)误判歧义、白白升级烧钱。新逻辑：blur≥400 自信 Pass、≤30 自信 Fail、之间才升级。
- 新增 `diagnosis/diagnose/training/evaluate_ambiguous.py`：从最清晰 feed 截图程序化合成渐进高斯模糊
  (核 0/3/5/7/9/13/19/27)，对比 rule / cascade(→真Qwen) / qwen_always 在"该不该判模糊"上的准确率/成本/延迟。

**证据**
- 校准后 clean 14-set：cascade 升级率 **57% → 0%**，avg_ms **692 → 13**（≈rule_only），verdict 仍 100%、visual 仍 71.43%（无精度损失）。浪费的 Qwen 开销清零。
- 歧义带 8 样本（`diagnosis/diagnose/training/reports/ambiguous_evaluation.json`，real_qwen=True）：

  | oracle | blur_acc | avg_ms | 升级率 | cost$ |
  |---|---|---|---|---|
  | rule_only | 87.5% | ~14 | 0% | 0 |
  | **cascade** | **87.5%** | **334** | **25%** | **0.0022** |
  | qwen_always | 87.5% | 1214 | 100% | 0.0088 |
  - 升级**精准命中**歧义带：仅 k03(blur=141)、k05(blur=64.5) 升级；k00 清晰/ k07+ 已极模糊都自信直出。
  - cascade **以 1/4 成本、1/4 延迟达到 qwen_always 同等准确率** → C4 cascade 的 cost-accuracy 价值证实。
- 回归：`diagnosis/tests` 76/76 仍通过。

**诚实发现（不许overclaim）**
1. **Qwen 不"严格"在准确率上碾压规则**：三者在歧义带都 87.5%。Qwen 修正了规则在 k03 的假阳(把清晰页误报模糊)，
   但在 k05 边界与合成 GT 不一致(漏报)。所以**当前能站住的 claim 是"cost-accuracy 等价 + 错误画像不同"，不是"更准"**。
2. 测试集仅 1 基底 × 8 核，是 proof-of-concept；要让结论稳需扩样本（已进 backlog P1）。
3. 真正的 cascade 价值 = **继承规则在自信区的免费快判 + 只在 25% 歧义带花钱问 Qwen**，整体逼近全 Qwen 精度而省 75% 成本。

**复现**: `DASHSCOPE_API_KEY=<key> python diagnosis/diagnose/training/evaluate_ambiguous.py`
（key 也会自动从仓库根 qwen.md 读，可不显式设）。

### Round 6 — 再找几个免改 appid 的小程序 + 定位截图 flaky 根因 + connect 模式
**日期**: 2026-05-27

**做了什么**
- 明确"免改 appid"判据 = **原生 + 无 npm + 无云开发**（wxapp-mall 即是；tdesign 因 build-npm 触发开发者权限校验才要改）。
- 程序化挖 `awesome-github-wechat-weapp` 列表 + GitHub API 自动筛"原生/无云/根有 app.json"：多数命中是**组件 demo**（日历/图表/抽屉等），
  真实多页 app 稀缺。新 staged `third-youzouzou-wxapp`（48 页组件画廊，无 npm/无云，原仓库无 project.config.json → 补建了一个用自有 appid）。
- 候选菜单（免改/少改 appid）：`third-wxapp-mall`(原生,✅已出结果) / `third-youzouzou-wxapp`(原生,staged) / `third-tdesign-retail`(原生官方,需 build-npm+改 appid,staged)。
- `run_foreign_matrix.py` 加 `--connect`（auto_relaunch=False，连已开 devtools 不重启）。

**关键发现：截图 flaky 的根因（重要，已确认非偶发）**
- 连跑 5 次：**只有用户手动开着前台 devtools 的第一个会话能 screen_shot**；此后 Minium 自己 relaunch 的会话 screen_shot 一律"返回成功但不写文件(last_err=None)"。
- 排除了"孤儿进程"假设：彻底清掉 15+ 个孤儿 `WeChatAppEx` + 所有 wechatdevtools 后，重启的会话**仍然**截不了图 → **不是孤儿进程问题**。
- 结论：这是 minium + 微信开发者工具的已知环境问题（Minium 后台 relaunch 的实例截图子系统坏掉）。**自动化侧无法修**，必须连用户手动开的前台健康实例。
- **可靠工作流（需用户）**：用户手动开 devtools（前台可见）→ 加载某项目 → 我用 `--connect` 连上跑：
  `python auto_test/v2_modules/run_foreign_matrix.py --project <dir> --tag <t> --qwen --connect`
  一个 app 一个会话；要换 app 就在 devtools 里手动打开下一个项目再跑。
- ✅ **connect 模式已验证可截图**：用户手动开 third-youzouzou-wxapp 后 `--connect` 跑通，截图正常。

**youzouzou-wxapp 结果（第 2 个独立原生 app，2 个 tabBar 页 others/example）**
- attach 100%；**verdict FP 100%（两页都误报 RenderBug）/ baseline FP 0%（SSIM=1.0）/ webug FP 0%**。
- 与 wxapp-mall 合并看，跨两个独立原生 app 高度一致：

  | app | verdict_fp | baseline_fp | webug_fp |
  |---|---|---|---|
  | wxapp-mall | 50% | **0%** | 75% |
  | youzouzou | 100% | **0%** | 0% |

  → **baseline 自比对跨 app 0% 假阳（唯一泛化通道）；verdict 通道在真实健康页过度报 RenderBug（50–100%）**。

**Round 6 修复 + 真机复测（before/after，重要）**
- 修复：`triage.py` 给 feed 的 `edge_too_low→is_blur` 加 `EDGE_BLUR_GUARD=400` 守卫——仅当全屏 Laplacian 方差 < 400（不够清晰）时低边缘密度才算模糊；清晰但稀疏的真实页不再误判。
- 回归：demo 14/14 verdict 仍 100%，`diagnosis/tests` 76/76 通过 → **不破坏 demo**。
- **真机复测（youzouzou，connect 模式）：verdict 假阳 100% → 0%**（两页都正确 Pass），baseline/webug 也 0% → any-channel FP 0%。
- wxapp-mall 离线复测：仍 50%——但根因**不同**（不是 edge 路径）：`category` 页 brightness=254 被**白屏检测**误判 bw=True；`user` 页 blur_full=58<100 是**稀疏近白页全屏方差低**被当模糊。这是第二套机制，更深。

**新 backlog（P1）**：第二套真实页假阳机制——白屏检测在合法白底页误触发、低全屏方差在稀疏近白页误判模糊。
需 content-aware oracle（仅在有内容/文字区域判模糊；仅在完全无内容时判 blank），改 blank 检测有 demo 回归风险，需谨慎。当前 baseline 通道(0%)可兜底。

### Round 5 — 真机跑独立小程序：wxapp-mall 跑通（跨框架 attach + 分通道假阳率）✅；tdesign 被截图 flaky 卡住 ⚠️
**日期**: 2026-05-27（用户开了微信开发者工具，交给我跑）

**wxapp-mall（原生 WXML，真正独立第三方 app）——完整结果**
- **零侵入 attach 成功率 100%**：Minium 0 行集成驱动，遍历全部 4 个 tabBar 真实页（home/category/cart/user）并诊断。
  → wxapp-mall 是**原生**小程序（非 uni-app），首次证实 driver **跨框架 attach**（此前两个验证目标都是 uni-app）。
- **健康页分通道假阳率**（Qwen cascade 开启，screenshots @ `reports/v2_driver/wxapp_foreign_20260527_010122/`）：

  | 通道 | 假阳率 | 解读 |
  |---|---|---|
  | baseline（与自身基线对比） | **0%** | SSIM=1.0 全绿 → **唯一 app-无关、可信**的零侵入通道 |
  | verdict（五分类主输出） | **50%** | category/user 两个**稀疏页**被误判 RenderBug（与 Round 2 同根因：稀疏页 edge_density 低被当模糊） |
  | webug（R1/R2/R3 辅助） | **75%** | R2 布局规则在内容丰富页必触发（无 DOM 像素 hack，且 scrollHeight>clientHeight 本就是正常滚动） |

- **核心结论（诚实，重要）**：三通道里**只有 baseline 自比对真正泛化（0% 假阳）**；verdict / webug 在真实健康 app 上过度报警，
  因为阈值是在合成 demo 上调的。→ "工程可用"的真相是：**零侵入 attach+诊断管线能跑通任意框架小程序，但开箱即用的判定通道会在真实 app 上乱报，必须按真实基线重新校准**。

**tdesign-retail（原生官方零售模板）——部分**
- ✅ `npm install`(445) + devtools CLI `build-npm` 成功（先把 project.config.json 的 appid 从 Tencent 的 `wx0ee80a2f23dbd157` 改成用户自有 `wx5a7ba069ebebaee5`，否则 build-npm 报"登录用户不是该小程序的开发者"）。
- ✅ Minium attach 成功（能 launch+连上+切页）。
- ⚠️ **screen_shot 截图全失败**（连续 8 次"截图重试 3 次失败/last_err=None"）：这是 minium 已知 flaky——
  **只有用户手动开着 devtools 的第一个 cold session 能截图**；我 taskkill + CLI relaunch 之后截图子系统就坏了，warmup 延时也没救回来。
- 解法（需用户）：完全关掉微信开发者工具 → 手动重新打开并加载 `third-tdesign-retail` 项目（让模拟器真正渲染）→ 再跑：
  `python auto_test/v2_modules/run_foreign_matrix.py --project D:/weixinmp_test/third-tdesign-retail --tag tdesign --qwen`
  （不要让我中途 taskkill；让 Minium 连已开的实例）。

**runner 修复（本轮）**：`run_foreign_matrix.py` 修了 baseline key bug（save/diagnose 都用 ptype，ssim 不再 None）、
改为**分通道**报假阳率（verdict/baseline/webug）、加了 relaunch 后 warmup。离线用 wxapp 真实截图复核了分通道数字。

### Round 4 — 预备两个独立小程序 + 发现并诚实化"零侵入"能力边界 ✅
**日期**: 2026-05-27

**做了什么**
- tarball 下载并 staged 两个独立开源小程序（git clone 走本机代理 127.0.0.1:7897 失败，改用 urllib 直连 codeload）：
  - `third-tdesign-retail/`（Tencent 官方零售模板，原生，useMock 自带数据，已 `npm install` 445 包，待 devtools "构建 npm"）
  - `third-wxapp-mall/`（lin-xin 商城，原生纯静态，无需 build，可直接开）
  - 两者 tabBar 都是 home/category/cart/user 四页，appid 均有效。加了 `.gitignore`。
- 读懂 driver 接入路径，**发现关键能力边界**（见下），据此新增 `auto_test/v2_modules/run_foreign_matrix.py`：
  零集成 attach + 从 app.json 自动读 tabBar 页 + 遍历真实页跑多通道诊断（learned/baseline/webug + `--qwen` 接 cascade）+
  算**健康页面假阳率**。离线已验证 app.json 页面解析对两个 app 都正确。

**关键发现（诚实化中心 claim，重要）**
- 旧 `run_real_matrix.py` **耦合 demo-uniapp**：页面路径硬编码 feed/counter/layout，8 类故障靠本项目 FastAPI 后端注入。
  之前的"foreign-uniapp"其实是 demo 的**再皮肤化副本**（保留了我的故障 hook）——所以"跨小程序"证据比看起来弱。
- **真正独立的第三方小程序无法零侵入注入故障**：小程序运行时是沙箱（无 DOM/CSS 注入），且 tdesign/wxapp-mall
  用本地 mock/静态数据（无 wx.request 可被 Minium 拦截）。→ 对任意 app 的零侵入故障注入**基本不可行**。
- 因此对独立 app，零侵入 driver 能诚实验证的是：**①0 行集成 attach ②真实页面多通道诊断跑通 ③健康页面假阳率**。
  这把"在任意小程序检出故障"降级为"在任意小程序零集成接入+诊断+低假阳"，是更站得住的 claim。

**待人类**：开微信开发者工具后跑（tdesign 需先在工具里"构建 npm"）：
- `python auto_test/v2_modules/run_foreign_matrix.py --project D:\weixinmp_test\third-wxapp-mall --tag wxapp --qwen`
- `python auto_test/v2_modules/run_foreign_matrix.py --project D:\weixinmp_test\third-tdesign-retail --tag tdesign --qwen`

### Round 3 — 研究可辩护：4 篇论文精准定位 + 红队答辩 + 候选小程序 ✅
**日期**: 2026-05-26

**做了什么**
- 联网核实 4 篇论文的真实 contribution（不再靠记忆）：
  - WeDetector/WeBug(ICSE'22)=**静态**查 3 类源码 bug 模式；WeReplay(FSE'23)=图像 **DL** 判**渲染态**服务重放时序；
  - MiniScope(TOSEM'24)=**静态+动态混合**查**隐私不一致**；WeMinT(ASE'23)=**静态污点**查数据泄漏。
- 重写 `docs/结题报告.md §7`：分 7.1（小程序生态四篇）+ 7.2（视觉/分诊/注入），每条给"vs X my delta Y"+核实事实；
  加一句话定位（四簇 prior work 都不做"运行时多模态维度分诊+零侵入 driver"）。
- 更新 §8 stale 的 Cascade 数据为真 Qwen + 校准后的真实数字。
- 产出 `docs/红队答辩.md`：6 类攻击逐条 问→诚实答→还需补，并列"能站住 vs 必须降级"的 claim 清单。
- 搜得 3 类候选开源小程序供下一轮真机验证（见 backlog P0）。

**证据**
- §7 现含 WeDetector/WeReplay/MiniScope/WeMinT 四篇精准 delta（之前只有 WeDetector 且事实有误）。
- `docs/红队答辩.md` 落盘；其"必须降级"清单直接修订了对外 claim。

**诚实发现（红队产出，已进 backlog）**
1. 必须降级："MLLM 更准"→"cost 等价+错误画像不同"；"跨小程序通用"→"跨 uni-app 通用"（待原生小程序）。
2. 待补证据：learned vs rule 显著性检验；与 Trident/WeDetector 同台对比；非合成歧义集 + 人工标注。
3. 第 3 个验证目标**优先原生 WXML 小程序**（lin-xin/wxapp-mall）才能把通用性 claim 升级到"跨框架"。
