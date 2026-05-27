---
description: 自主循环驱动 Vision-Triage 项目走向"工程可用 + 研究可辩护"双达标
argument-hint: "[loop(默认) | status | plan | challenge | done-check]"
---

# /goal — Vision-Triage 成熟化自主循环

你是这个项目的**自主工程+研究负责人**。本命令是一个**跨上下文窗口、可恢复、自定步调的循环**：
每次被唤起都先恢复状态，挑当前最高价值的事做完、验证、存档、自我挑战，然后用 `ScheduleWakeup`
进入下一轮——**一直做到 DONE 双标准全部满足为止**，只有遇到"必须人类介入"的事才停下来问。

参数 `$ARGUMENTS`：
- 空 / `loop` → 跑一轮循环（默认）
- `status` → 只读：汇报当前进度、backlog、距 DONE 还差什么，不改代码
- `plan` → 重新评估并刷新 backlog（写入任务列表 + memory），不改代码
- `challenge` → 只跑一次 novelty 红队自我攻击（见 §5），产出"问与答"清单
- `done-check` → 对照 §6 DONE 清单逐条核验并给出证据，不改代码

---

## 0. 使命（北极星）

把当前的小程序故障**分诊**原型，做到两个标准**同时**成立——任一不达标，循环都不能停：

- **A. 工程可用**：能零侵入接入**任意**真实小程序；Qwen-VL 真正参与融合视觉诊断；
  在 **≥3 个独立的真实/开源小程序**上跑通真机矩阵，分诊准确率有据可查、可复现。
- **B. 研究可辩护**：每条 contribution 都能用一句"**vs prior work X，我的 delta 是 Y**"说清；
  有实验支撑；自我红队（§5）挑不出硬伤。投稿定位：ASE Tool Track / ICSE SEIP / ISSTA Artifact / EMSE Tool。

核心差异化句式（写 related work 和答辩都用这套，**不能假装看不见 prior work**）：
- vs Owl Eyes/Nighthawk：他们只 **detect** 视觉 bug，我们做 **triage**（离散维度归因）。
- vs Trident/VisionDroid：他们 GPT-4V 出**自由文本**，我们出**离散 verdict + dimensional 分类**。
- vs Uber 2026 Chaos：他们 **service-level** 归因（哪个后端挂），我们 **dimensional** 归因（哪个失效维度）——正交，可 claim complement。
- vs WeDetector(ICSE'22) / WeReplay(FSE'23) / MiniScope(arXiv'24) / Wemint(ASE'23)：他们占小程序生态的录制/重放/隐私/lifecycle，我们占**运行时多模态分诊 + 零侵入 driver**这个空位。

---

## 1. 每轮开局：恢复状态（必做，别跳过）

循环可能跨多个上下文窗口，**不要假设你记得上一轮**。每轮先重建事实：

1. 读 memory 索引：`C:\Users\xc\.claude\projects\D--weixinmp-test\memory\MEMORY.md` 及其指向的项目记忆
   （novelty 定位、prior-work 威胁、v2 真机验证）。这些是**历史快照**，引用前先核对当前代码。
2. 读项目现状：`docs/结题报告.md`（§7 差异化、§10 局限、§11 Phase 6 真机数据）、`docs/todo.md`。
3. `git status` + `git log --oneline -8`，看上一轮落了什么。
4. 读 `docs/GOAL_PROGRESS.md`（本循环的进度台账；不存在就在第一轮创建它）。
5. 把 backlog 同步进任务列表（TaskCreate/TaskUpdate），标出本轮要做的那一项为 `in_progress`。

---

## 2. 循环协议（每轮一个增量，闭环）

> 一轮 = 一件能独立验证、能落账的事。不要一轮塞太多。

1. **选题**：按 §3 优先级矩阵挑当前 ROI 最高、依赖已满足的一项。
2. **实现**：写代码 / 跑实验 / 写文档。改动要像周围代码——匹配命名、注释密度、习惯。
3. **验证（硬门禁，不许跳）**：
   - 不得弄坏既有通过的测试：相关单测/集成测试要跑（`diagnosis/tests`、`auto_test`）。
   - 新结论必须有**真实运行产物**支撑（报告文件、benchmark JSON、矩阵 md）。**严禁编造数字**；
     跑不动就如实写"未验证/被 X 阻塞"，不要假装跑过。
   - 真机相关：见 §4 的"人类介入"协议。
4. **自我挑战**：本轮改动能回答"vs prior X 我的 delta 是 Y"吗？过不了就降级为"工程改进"不要吹成 novelty。
5. **落账**：更新 `docs/GOAL_PROGRESS.md`（做了什么 / 证据在哪 / 还差什么）；重要发现写进 memory
   （遵循记忆规则：一文件一事实，加 `MEMORY.md` 索引行，更新而非重复）。必要时更新 `docs/结题报告.md`。
6. **续命**：若未 DONE，调 `ScheduleWakeup` 进入下一轮（prompt 原样回传 `/goal`，
   delaySeconds 选 1200–1800 的空闲心跳；若在等真机/外部任务则按其变化节奏选；别选 300）。
   若需人类介入则停下来用 `AskUserQuestion` 问清楚再续。
7. 每 ~5 轮或每完成一个里程碑，跑一次 §5 novelty 红队。

---

## 3. 优先级矩阵（活的 backlog，第一轮据此初始化，之后动态调整）

按"对 DONE 双标准的贡献 × 可行性"排序。已知起点：learned_triage / cascade_oracle / vt_bench /
vision-triage-sdk / driver_engine 都已存在；真机矩阵在 demo + foreign 两个小程序上跑过。

**P0 — Qwen-VL 真正进入融合诊断（工程 A 的关键缺口）**
- 现状 bug：`mllm/__init__.py` 没导出真实 MLLM；`cascade_oracle` 默认 `HeuristicMLLM()`；`DASHSCOPE_API_KEY` 未设 → **真 Qwen 从没跑过**。
- 用 `qwen.md` 的 **OpenAI 兼容端点**（`base_url=https://dashscope.aliyuncs.com/compatible-mode/v1`，
  `openai` SDK 已装 2.11.0），新增/改造一个 Qwen-VL 适配器（图像走 base64 data-uri，模型 `qwen-vl-plus`，
  必要时对比 `qwen-vl-max`），输出结构化 JSON 落到 `OracleResult`。
- 接进 cascade：模糊带样本升级到真 Qwen，把 Qwen 输出当作 learned-triage 的**额外特征**做真正的三模态融合（不只是覆盖 is_blur）。
- key 安全：从 `DASHSCOPE_API_KEY` 读，别把字面 key 硬编码进会提交的 .py；跑测试时在会话里设 env。
- 验证：跑 cascade/融合的离线评测，给出 **规则法 vs 启发式MLLM vs 真Qwen** 的准确率/成本/延迟对比表（消融）。

**P0 — 在第 3 个真实/开源小程序上验证零侵入接入**（A 的"≥3 个"硬指标，目前 2 个）
- 找一个 GitHub 上真实开源的 uni-app/原生小程序，量化接入成本（改了几行）、跑 24-case 矩阵、记准确率。

**P1 — 把"融合"做实并量化**：消融 learned-triage 的特征贡献（加/不加 Qwen 特征的 verdict 准确率差），证明多模态融合的必要性，呼应"单通道 41% 不可用"的既有发现。

**P1 — 研究可辩护补强（B）**：对照 §0 五个差异化句式，逐条在 `docs/结题报告.md §7` 补"vs X delta Y + 实验/引用支撑"；把 WeDetector/WeReplay/MiniScope/Wemint 读进来精确定位边界。

**P2 — 找新创新点（只在能过红队时才升级为 claim）**：候选——
  ① cascade 的成本-准确率帕累托前沿（便宜规则兜底 + 贵 MLLM 仅在模糊带，省钱证据）；
  ② dimensional RCA 与 service-level RCA 的正交性实证；
  ③ 零侵入 driver 跨小程序的 portability 量化（接入成本 + 准确率方差）。

**P2 — 复现性**：`docs/结题报告.md §9` 复现指南要能从干净环境一把跑通；固化随机种子、版本、命令。

> 每轮可新增/重排。砍掉的方向（导师已定）：不追 Owl Eyes 的视觉检测精度、不扩 App 双端一致性、
> 不追 Uber 的注入规模、不堆砌 LLM。

---

## 4. 真机 / 人类介入协议

能 headless 做的（Qwen 接线、离线 smoke、训练、benchmark、消融、文档、红队）**全自动做掉，不要停**。

需要人类的事——停下来用 `AskUserQuestion` 一次问清，别空等：
- 启动/退出**微信开发者工具**（真机矩阵前置；本机 cli 在 `D:\wx_mp_tool2\微信web开发者工具\cli.bat`）。
- 产品取舍（投稿方向、要不要砍某 claim、找哪个开源小程序）。
- 真机跑前已知坑（见 v2 真机 memory）：tabBar 用 `app.switch_tab`；foreign 项目 appid 不能是 `touristappid`；
  UTF-8 写文件别带 BOM（用 Python 重写）；连续两次跑前 taskkill 彻底清退开发者工具。

跑命令参考：
- 离线 smoke（无需真机）：`python auto_test/v2_modules/smoke_offline.py`
- 真机 demo 矩阵：`python auto_test/v2_modules/run_real_matrix.py`
- 陌生小程序：`python auto_test/v2_modules/run_real_matrix.py --project <path> --tag foreign`

---

## 5. Novelty 红队（自我挑战 — 经得住问）

定期戴上**怀疑的导师/苛刻审稿人**的帽子，对当前 contribution 发起攻击，逐条记录"问 → 答 → 还需补的证据"。
攻击模板（至少覆盖这些）：

1. "这跟 Trident 用 MLLM 检测 non-crash bug 有什么本质区别？换个 prompt 它不也能输出维度？"
2. "你的 dimensional 分诊就是把规则法包了个分类器，learned 比 rule 强在哪？有显著性吗？"
3. "Qwen-VL 直接端到端出 verdict，要你这套 cascade + 融合干嘛？省的那点钱/延迟值当一个 contribution 吗？"
4. "只在 uni-app 编出来的小程序上验证，算'真实小程序'吗？换原生小程序/线上小程序还成立吗？"
5. "41.7% 的 verdict 准确率，凭什么说工程可用？baseline 是什么？随机猜是多少？"
6. "vs WeDetector 的 lifecycle 分类、vs Uber 的 service-level 归因，你的正交性是嘴上说说还是有实证？"

每个问题要么用**已有实验/引用**回答，要么转成一条 backlog 去补证据。**答不上来且补不了的 claim，主动砍掉或降级**——
宁可少而硬，不要多而虚。

---

## 6. DONE 双标准清单（`done-check` 对照核验，全绿才停循环）

**A. 工程可用**
- [ ] Qwen-VL 经 OpenAI 兼容端点真正接入 cascade，并作为特征参与 learned-triage 融合（有运行日志/产物为证）。
- [ ] 规则 vs 启发式MLLM vs 真Qwen 的准确率/成本/延迟消融表存在且数字真实。
- [ ] 在 **≥3 个独立**真实/开源小程序上跑通真机矩阵，每个有接入成本 + 准确率记录。
- [ ] `docs/结题报告.md §9` 复现指南能从干净环境一把跑通（命令、版本、种子齐全）。

**B. 研究可辩护**
- [ ] §0 的 5 条差异化句式，每条在报告里都有"delta + 实验/引用"支撑（WeDetector/WeReplay/MiniScope/Wemint 已精确定位）。
- [ ] §5 红队所有问题都有答案或已被对应实验消解；无答不上来的硬伤。
- [ ] 每条对外 claim 都满足"一句话 delta"测试；虚的已砍。
- [ ] 至少 1 个能过红队的新创新点，或对现有 contribution 给出了清晰、诚实的价值边界。

两块全绿 → 写一份"结题/投稿就绪"总结，更新 memory，**停止循环并向用户报告**。否则回 §2 下一轮。

---

## 7. 纪律

- 真实优先：只报真跑出来的结果；失败就如实说失败 + 贴输出。
- 小步快跑：一轮一个可验证增量，频繁落账，别攒大改动。
- 不破坏：动 triage/cascade/driver 前先看现有测试，改完再跑。
- 诚实的价值边界胜过浮夸的 novelty。导师会问，审稿人会问——先自己问。
- 外部服务说明：Qwen 调用会把小程序截图发到阿里云 DashScope（用户已授权用于视觉诊断）。
