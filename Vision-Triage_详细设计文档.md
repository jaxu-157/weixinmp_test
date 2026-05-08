# Vision-Triage Demo 与自动化测试平台详细设计文档

> 面向 uni-app 微信小程序的“分诊式测试预言”原型
基于功能断言、性能断言与视觉断言的故障分诊设计

## 0. 文档定位

本文把当前项目从“开题报告”推进到“可以实际开工的开发设计文档”。目标不是再论证题目，而是把下面三件事写清楚：

1. **Demo 小程序到底做什么、怎么做、做到什么程度算完成**
2. **自动化测试平台如何搭起来，并且如何和视觉诊断、性能取证串起来**
3. **现有开源项目里哪些应该直接复用、哪些只适合借鉴、哪些不建议作为主底座**

本文默认项目名称沿用开题版本 **Vision-Triage**，并保留你们报告中的核心方向：  
**围绕“页面卡顿、白屏、模糊、错位、显示旧数据”等表象，通过功能断言、性能断言、视觉断言实现小程序故障分诊。** [R1]

---

## 1. 项目背景、目标与范围

### 1.1 背景

开题报告已经把问题定义得很准确：在小程序测试中，测试人员会遇到“页面卡顿”“图片模糊/马赛克”“数据显示错位”“白屏”等现象，但很难快速判断到底是：

- 后端接口异常
- 前端业务逻辑 Bug
- 小程序平台运行时性能约束导致的问题

这会造成误诊，把“性能触顶”误判为“代码写错”，浪费排查时间。[R1]

### 1.2 项目目标

本项目要做的不是另一个“通用小程序测试框架”，而是一个**可运行的课程级原型**，核心目标如下：

- 开发一个 **uni-app 微信小程序 Demo**
- 为 Demo 设计 **功能断言 + 性能断言 + 视觉断言**
- 构建一个 **自动化执行与证据采集平台**
- 对可控故障样本输出分诊结果：
  - `Pass`
  - `FunctionalFail`
  - `PerformanceRisk`
  - `Mixed`
  - （可选）`RenderBug` / `Unknown`

### 1.3 非目标

第一版不做这些内容：

- 不做 App 与小程序双端一致性实验
- 不做大规模云端设备农场
- 不做真正意义上的系统级混沌工程
- 不做基于 LLM 的复杂预言自动生成器
- 不把 minium / automator / MCP 全部接进来，只做最小可跑通组合

### 1.4 成功标准

第一版达到以下结果，就算项目成功：

1. 小程序端有 **3 个可演示页面**
2. 至少支持 **4~6 类故障注入**
3. 自动化脚本能完成：
   - 切换故障模式
   - 打开页面
   - 触发关键操作
   - 读取功能结果
   - 保存性能指标
   - 截图
   - 调用 Python 诊断器
4. Python 诊断器能对至少 3 类视觉异常给出稳定判断：
   - 黑/白屏
   - 模糊
   - OCR 文本不一致
5. 结题时能构造“已知根因”的实验样本，展示本方法比传统单一功能断言更少误判。[R1]

---

## 2. 总体方案与核心结论

## 2.1 最终推荐架构

本项目推荐使用下面这条“**三层架构**”：

```text
uni-app Demo 小程序
  ├─ 业务页面（图片流 / 数据更新 / 布局压力）
  ├─ 故障开关（fault profile）
  ├─ 页面状态导出
  └─ 微信专用性能埋点（仅 MP-WEIXIN）

Node 自动化执行层
  ├─ Jest
  ├─ miniprogram-automator
  ├─ case 编排
  ├─ 截图与证据归档
  └─ 调用 Python 诊断服务

Python 诊断与注入层
  ├─ FastAPI
  ├─ mock API / fault profile 管理
  ├─ OpenCV 视觉判断
  ├─ PaddleOCR 文字识别
  └─ triage verdict 生成
```

这是最适合你们现阶段的组合，原因如下：

- **uni-app**：你已经确定要用，而且它本身就是“一套代码编译到微信小程序”等多端框架；官方 CLI 直接支持 Vue3 + TypeScript 模板。[R2][R3]
- **miniprogram-automator + Jest**：轻量、直接、资料多，足够支撑课程项目自动化执行。[R5]
- **FastAPI + OpenCV + PaddleOCR**：把“故障注入 / 视觉诊断 / 诊断 API”集中在 Python 侧，结构清晰，便于分工。[R13][R14]

## 2.2 为什么不建议“从头全手搓”

现有公开项目已经分别提供了这些能力：

- **小程序自动化执行**：miniprogram-automator、minium、FAutoTest [R5][R6][R22]
- **Mock / 等待 / 自动化增强**：mpx-e2e [R7]
- **组件级单元测试**：miniprogram-simulate [R8]
- **页面截图 / Console / 网络追踪 / 断言**：weixin-devtools-mcp [R9]
- **性能与异常观测**：wx.getPerformance、wx.onMemoryWarning、性能诊断工具、sentry-miniapp [R10][R11][R12][R21]

因此本项目真正应该自己做的，不是底层驱动，而是：

1. **故障样本构造**
2. **三重断言的证据融合**
3. **分诊决策逻辑**
4. **实验与误诊率对比**

也就是说：  
**底座复用，分诊核心自研。**

---

## 3. 技术栈与工具选型

## 3.1 Demo 小程序技术栈

### 推荐组合

- **uni-app**
- **Vue 3**
- **TypeScript**
- **最少量 UI 组件**
  - 官方 `uni-ui` 即可
  - 不建议一上来引入过多组件库

### 为什么这样选

uni-app 官方支持通过 CLI 创建 Vue3 + TypeScript 工程，命令模板为 `dcloudio/uni-preset-vue#vite-ts`，并通过 `npm run dev:mp-weixin` 运行到微信小程序。[R3]

同时，uni-app 支持 `#ifdef MP-WEIXIN` 条件编译，可以把微信专用的观测、注入和调试逻辑隔离出来，不污染其他平台代码。[R4]

### 推荐初始化方式

```bash
npx degit dcloudio/uni-preset-vue#vite-ts vision-triage-demo
cd vision-triage-demo
npm install
npm run dev:mp-weixin
```

### 备选工程模板

- **hello-uniapp**：官方全量示例，适合快速找页面模式与 API 用法。[R15]
- **hello-unibest**：适合更工程化团队协作，内置 Vue3 + TS + Vite + z-paging + 路由与请求封装。[R16]
- **ITxChen/uni-app-vue3-ts**：完整商城模板，适合借鉴列表页、详情页、数据刷新交互。[R19]

### 最终建议

**主项目用官方 vite-ts 模板开新仓库。**  
其他模板只做“参考与代码借用”，不要直接魔改一个大商城项目，否则会引入大量与你们课题无关的状态和页面。

---

## 3.2 自动化测试平台技术栈

### 推荐组合

- **Node.js**
- **Jest**
- **miniprogram-automator**

### 为什么这样选

现有实践中，miniprogram-automator 被当作微信小程序自动化测试框架使用，可以与 Jest 一起组织用例；自动化前需要微信开发者工具开启服务端口，或通过 CLI 启动自动化端口。[R5]

### 推荐定位

把它当作本项目的**主执行器**，做下面几件事：

- 激活 fault profile
- 打开目标页面
- 触发点击、刷新、滚动等动作
- 读取页面文本/状态
- 截图
- 保存性能 JSON
- 调用 Python 诊断 API
- 输出最终 verdict

### 为什么不优先选 Minium 当主执行器

Minium 很强，支持获取/设置页面数据、直接触发元素事件、注入 AppService 代码、调用部分 `wx` 接口。[R6]  
但它更适合做第二阶段的增强调试或深度注入；第一版如果把 Minium 当主执行器，学习成本会略高。

### Minium 的正确位置

- 第一版：**可选增强工具**
- 第二版：如果你们想做更深的页面数据篡改、脚本注入、细粒度观察，再接入

---

## 3.3 Python 诊断与 Mock 技术栈

### 推荐组合

- **Python 3.11**
- **FastAPI**
- **OpenCV**
- **PaddleOCR**

### 为什么这样选

FastAPI 是高性能 Python API 框架，自带 OpenAPI 文档能力，非常适合作为“本地 mock / 故障开关 / 诊断服务”的统一入口。[R14?]

OpenCV 已原生提供 `cv::Laplacian` 等图像处理能力，可用于模糊检测；`matchTemplate` 可用于模板匹配，适合页面关键区域对比。[R13]

PaddleOCR 是成熟的 OCR 工具，支持 100+ 语言，中文界面识别足够实用。[R14]

### 建议定位

Python 服务同时承担两类职责：

1. **故障注入 API**
2. **视觉诊断 API**

这样你们只维护一个后端进程。

---

## 3.4 可选增强工具（第二阶段）

- **mpx-e2e**：如果你们后续需要更方便的 mock 能力，可以参考其对 miniprogram-automator 的封装。[R7]
- **miniprogram-simulate**：适合补组件级单元测试，验证局部组件在正常/错误输入下的纯功能表现。[R8]
- **weixin-devtools-mcp**：适合后续接入更丰富的 Console / Network / screenshot / assert 能力，但第一版不是必需。[R9]
- **sentry-miniapp**：适合补充异常与性能上下文采集，尤其适合做长期观测而非第一版核心依赖。[R21]
- **wxapp-boot-time**：可作为“视觉法也能测启动性能”的参考案例，不建议直接集成到第一版。[R23]

---

## 4. 现有开源项目与推荐复用方式

## 4.1 直接采用的项目

| 项目 | 作用 | 本项目使用方式 | 结论 |
|---|---|---|---|
| uni-app vite-ts 模板 | 创建 Vue3 + TS 工程 | 直接作为主工程起点 | **直接采用** |
| miniprogram-automator | 驱动微信开发者工具中的小程序 | 直接作为 E2E 执行器 | **直接采用** |
| Jest | 测试组织与断言 | 直接作为测试框架 | **直接采用** |
| z-paging | 下拉刷新、上拉加载、虚拟列表 | 图片流/数据列表页面直接使用 | **直接采用** |
| PaddleOCR | OCR 识别 | 读取截图内数值/标题/状态文案 | **直接采用** |
| OpenCV | 视觉规则判断 | 黑白屏、模糊、模板对比 | **直接采用** |

## 4.2 参考采用的项目

| 项目 | 价值 | 适合借鉴什么 | 结论 |
|---|---|---|---|
| Minium | 自动化能力深、可注入页面数据 | 深度注入、页面数据篡改、脚本注入 | **第二阶段接入** |
| mpx-e2e | automator 增强封装，自带 mock | 等待策略、mock 设计 | **借鉴设计** |
| miniprogram-simulate | 小程序组件测试 | 组件级纯功能校验 | **局部采用** |
| sentry-miniapp | 异常/性能监控，多端兼容 | 性能与异常证据增强 | **可选** |
| weixin-devtools-mcp | 截图、Console、Network、断言 | 调试和回归增强 | **可选** |
| wxapp-boot-time | 视觉法测启动耗时 | 实验设计灵感 | **只参考** |

## 4.3 不建议作为主底座的项目

| 项目 | 原因 |
|---|---|
| FAutoTest | 框架较老，公开维护活跃度较低；适合了解微信内自动化的历史方案，不适合作为本项目核心底座。[R22] |
| 大型商城/管理系统开源项目 | 业务太重，改造成本高，容易把课题重心从“分诊”拖成“业务搬运”。 |

---

## 5. 符合要求的 Demo 样本与借鉴建议

这里的“样本”分成两类：

1. **工程模板样本**：帮你快速搭工程
2. **页面/组件样本**：帮你快速凑齐“图片流、数据更新、布局异常、分页加载”场景

## 5.1 最值得借鉴的样本

### 样本 A：hello-uniapp（官方示例）

- 类型：官方示例工程
- 价值：页面结构标准，工程结构干净，适合查 uni-app 组件和页面组织方式
- 适合用途：作为“查 API / 查页面写法 / 查 manifest/pages 配置”的参考工程
- 结论：**建议本地拉下来做对照，但不要直接在它上面开发课题 Demo** [R15]

### 样本 B：hello-unibest

- 类型：现代 uni-app 模板
- 价值：内置 Vue3 + TS + Vite + z-paging 等工程化能力，适合团队协作 [R16]
- 适合用途：如果你们更熟悉 VS Code / 命令行工具链，不想太依赖 HBuilderX，可参考其工程约定
- 结论：**可以参考目录结构与工程化配置，不建议整仓 fork 改造**

### 样本 C：ITxChen/uni-app-vue3-ts

- 类型：商城小程序模板
- 价值：天然带有商品列表、详情、登录、购物车、订单等“数据更新 + 列表交互”场景 [R19]
- 适合用途：借鉴列表页和详情页交互；也适合作为“复杂业务页面”的参考
- 结论：**非常适合借鉴页面结构，但第一版不要整仓接入**

### 样本 D：z-paging demo

- 类型：分页/虚拟列表样本
- 价值：官方 demo 目录里既有 Vue2/3 写法，也覆盖下拉刷新、上拉加载、虚拟列表等典型能力；仓库明确支持微信小程序，并能流畅渲染大量数据。[R17]
- 适合用途：直接做你们的 `feed` 页面底座
- 结论：**建议直接使用**

### 样本 E：uniapp-waterfalls-flow / uni-waterfall-flow / mp-waterfall / wx-waterfall

这几个项目不需要全用，但都非常有价值：

- **uniapp-waterfalls-flow**：现成 uni-app 瀑布流组件，适合直接上手 [R18]
- **uni-waterfall-flow**：明确提到 `setTimeout` 是为兼容页面渲染卡导致的定位不准问题，说明瀑布流场景很适合做“布局错位 / 图片尺寸变化 / 性能退化”的实验。[R18]
- **mp-waterfall**：适合“宽高不固定图片 + 多列布局”场景 [R18]
- **wx-waterfall**：明确指出长列表、大量图片、尤其动图场景会导致 `scroll-view` 卡顿，并给出懒渲染、图片懒加载、视图复用等优化方向。[R18]

- 适合用途：做 `feed` 页、`layout` 页
- 结论：**至少选一个直接用；wx-waterfall 作为性能风险设计参考**

### 样本 F：WeChatMeiZi

- 类型：非常简单的照片流 Demo
- 价值：结构极简，适合参考“图片流最小实现”
- 结论：**只适合作为简化版样例参考** [R18]

### 样本 G：matrixone_uniapp_demo

- 类型：完整的 uni-app 微信小程序示例
- 价值：前后端调用链完整，适合借鉴 API 通路
- 结论：**适合作为接口层参考，不建议直接套用** [R20]

## 5.2 最终样本组合建议

**最优组合：**

- 工程起点：官方 vite-ts 模板
- 列表能力：z-paging
- 瀑布流能力：uniapp-waterfalls-flow 或 mp-waterfall
- 页面交互参考：ITxChen/uni-app-vue3-ts
- API 联调参考：matrixone_uniapp_demo

---

## 6. Demo 小程序设计

## 6.1 页面清单

第一版只做 **3 个主页面 + 1 个调试面板**。

### 页面 1：图片流页 `pages/feed/index`

#### 目的
- 承载图片流、模糊、白块、加载慢、大图、滚动卡顿等现象
- 为视觉断言和性能断言提供主要场景

#### 页面元素
- 顶部筛选条
- 图片卡片瀑布流 / 双列流
- 标题
- 子标题/标签
- 封面图
- 加载状态
- 点击进入详情或弹层

#### 支持的故障
- `blur_image`
- `slow_api`
- `layout_overlap`
- `memory_pressure`
- `mixed_fault`

#### 对应断言
- 功能断言：卡片数量、标题存在、点击进入成功
- 性能断言：首屏加载时长、滚动性能、无内存告警
- 视觉断言：模糊、白屏、关键区域结构正确

### 页面 2：数据更新页 `pages/counter/index`

#### 目的
- 承载“显示旧数据”“数据更新正确但很慢”“按钮点击后无可见变化”等问题
- 是最适合做 OCR 校验的页面

#### 页面元素
- 当前计数/版本号
- 刷新按钮
- 最近更新时间
- 状态文本
- 调试信息区域（开发环境可见）

#### 支持的故障
- `stale_ui`
- `slow_api`
- `wrong_mapping`
- `mixed_fault`

#### 对应断言
- 功能断言：页面值应等于接口返回值
- 性能断言：从点击到界面可见文本更新的耗时
- 视觉断言：OCR 读取屏幕文本，确认显示值是否更新

### 页面 3：布局压力页 `pages/layout/index`

#### 目的
- 用于布局错乱、遮挡、元素位移、长文本溢出、错位等视觉异常场景

#### 页面元素
- 多列卡片区
- 长标题
- 标签
- 操作按钮
- 不同尺寸图片
- 自适应高度

#### 支持的故障
- `layout_overlap`
- `slow_render`
- `memory_pressure`
- `mixed_fault`

#### 对应断言
- 功能断言：元素存在且按钮可点击
- 性能断言：首屏和滚动性能不过阈值
- 视觉断言：关键区域模板匹配、元素偏移、遮挡

### 页面 4：调试面板 `components/FaultPanel.vue`

#### 目的
- 开发阶段手动切换故障模式
- 不参与正式实验
- 自动化脚本可不通过 UI，而是直接调用后端切换

#### 功能
- 当前 fault profile 显示
- 切换 profile
- latency 配置
- 图片质量开关
- stale UI 开关
- 内存压力开关
- 一键恢复 normal

---

## 6.2 页面间交互原则

- 每个页面都必须可以 **单独进入、单独测试**
- 每个页面都必须支持 **直接携带 query 参数进入**
- 每个页面都必须能导出一份 **当前页面状态 JSON**
- 页面不要过于业务化；目标是“好测、好截图、好解释”，不是“像真实电商那样完整”

---

## 7. 故障注入设计

## 7.1 为什么必须保留故障注入

自动化测试工具擅长的是“驱动页面、执行操作、采集结果”，但不负责给你稳定制造“已知根因”的实验样本。  
而本项目要验证的是**分诊能力**，不是单纯“会不会报警”。

如果没有故障注入，你很难证明：

- 为什么这次应该判成 `PerformanceRisk`
- 为什么那次应该判成 `FunctionalFail`
- 为什么某次应该判成 `Mixed`

因此故障注入不是为了替代自动化，而是为了构造**可重复、可控、已知根因**的样本。[R1]

## 7.2 fault profile 设计

建议统一使用下表中的故障模式：

| profile | 含义 | 使用页面 | 预期结论 |
|---|---|---|---|
| normal | 无故障 | 全部 | Pass |
| slow_api | 接口慢但结果正确 | feed/counter | PerformanceRisk |
| blur_image | 图像模糊但内容在 | feed | VisualFail / RenderBug |
| stale_ui | 接口返回新值，但页面仍显示旧值 | counter | FunctionalFail |
| wrong_mapping | 数据映射错误 | counter | FunctionalFail |
| layout_overlap | 样式错位/遮挡/重叠 | layout/feed | VisualFail |
| memory_pressure | 大图/大数组/大量节点导致内存压力 | feed/layout | PerformanceRisk 或 Mixed |
| mixed_fault | 同时注入功能和性能异常 | 全部 | Mixed |

## 7.3 注入位置

### 服务端注入（推荐主方式）

由 FastAPI 管理当前 `fault profile`，接口层按 profile 返回不同结果。

例如：

- `slow_api`：sleep 800ms ~ 1500ms 后返回正常数据
- `blur_image`：返回模糊版图片 URL
- `stale_ui`：正常返回新数据，但前端根据 profile 不提交可见状态
- `wrong_mapping`：返回字段名称与前端预期对不上
- `mixed_fault`：同时慢接口 + 错误渲染

### 客户端注入（辅助方式）

用于模拟更贴近渲染层或状态同步层的问题：

- 故意不提交某次可见状态
- 故意切换错误 class
- 故意保留旧缓存
- 故意创建过大的临时数组/对象

### 观测层注入（取证，不是制造故障）

- 监听 `wx.onMemoryWarning`
- 使用 `wx.getPerformance` 采集性能条目
- 结合开发者工具性能诊断和截图取证 [R10][R11][R12]

## 7.4 为什么不能把故障逻辑写满页面

uni-app 官方强调，多端差异和平台专有能力适合通过条件编译隔离；如果把平台分支和调试逻辑散落在页面里，会增加冗余和维护成本。[R4]

因此必须把故障注入统一收敛到 `services/fault.ts` 和 `services/api.ts` 里。

---

## 8. 观测与证据采集设计

## 8.1 证据类型

### 功能证据
- 页面状态 JSON
- 接口响应
- 页面文本值
- 元素存在性与可点击性

### 性能证据
- 交互到可见变化的耗时
- `wx.getPerformance` 的 navigation/render/script/resource 数据 [R12]
- `wx.onMemoryWarning` 告警 [R11]
- 开发者工具性能诊断截图或记录 [R10]

### 视觉证据
- 页面截图
- ROI 区域截图
- OCR 结果
- 模糊分数
- 模板匹配得分

## 8.2 关于 `wx.getPerformance` 的实现建议

不建议把性能断言建立在“包一层同步 `Date.now()`”的朴素测法上。  
公开实践指出，`wx.getPerformance()` 能获取 navigation/render/script/resource 等性能数据，但在 `Page.onLoad` 里直接取值可能拿不到当前页面完整数据；更稳的做法是在更早时机注册 observer，以事件监听方式获取指标。[R12]

因此本项目推荐的性能断言是：

1. **端到端交互延迟**
   - 点击刷新按钮 → 页面文本可见变化
2. **页面级性能指标**
   - navigation / render / script
3. **告警型指标**
   - 内存告警
   - 开发者工具性能诊断建议

## 8.3 页面状态导出协议

每个页面都提供一个统一方法（例如挂到全局或导出到调试对象），返回：

```json
{
  "page": "counter",
  "visibleValue": 2,
  "expectedValue": 2,
  "updatedAt": 1713600000,
  "faultProfile": "slow_api",
  "uiFlags": {
    "hasOverlap": false,
    "imageLoaded": true
  }
}
```

这样自动化层可以不依赖过多 DOM 细节，而直接拿业务状态。

---

## 9. 视觉诊断器设计

## 9.1 输入与输出

### 输入
- 页面截图
- 页面类型（feed / counter / layout）
- fault profile（仅实验阶段可见）
- 页面状态 JSON
- 性能 JSON

### 输出

```json
{
  "visual": {
    "black_white": false,
    "blur_score": 82.1,
    "ocr_text": "2",
    "template_score": 0.93
  },
  "functional": {
    "pass": true,
    "reason": ""
  },
  "performance": {
    "pass": false,
    "reason": "interaction_latency=1260ms"
  },
  "verdict": "PerformanceRisk",
  "explanation": "数据最终正确，OCR与状态一致，但交互延迟显著超阈值"
}
```

## 9.2 视觉规则设计

### 规则 1：黑/白屏检测
- 方法：灰度图均值或阈值统计
- 适合场景：全黑、全白、渲染层崩溃前后的极端画面
- 开题报告已把“全黑 / 全白”列为技术根因推断场景之一。[R1]

### 规则 2：模糊检测
- 方法：Laplacian 方差
- 理由：OpenCV 原生提供 Laplacian 算子，适合作为模糊度指标基础。[R13]

### 规则 3：OCR 数值校验
- 方法：PaddleOCR
- 适合场景：读取“当前值”“订单号”“状态文案”“页头标题”
- 理由：PaddleOCR 支持 100+ 语言，中文界面适配性好。[R14]

### 规则 4：模板/关键区域匹配
- 方法：OpenCV `matchTemplate`
- 适合场景：按钮错位、布局重叠、关键区域被遮挡
- 理由：模板匹配可用于在大图中查找关键模板位置。[R13]

## 9.3 第一版不做什么

第一版不要做：

- 深度学习布局检测
- 完整目标检测
- 复杂场景语义理解
- 多模型融合

课程项目里，**规则法足够**。

---

## 10. 分诊决策逻辑

## 10.1 三重断言定义

- `Afunc`：功能断言
- `Aperf`：性能断言
- `Avisual`：视觉断言

这与你们开题报告保持一致。[R1]

## 10.2 推荐 verdict 规则

| Afunc | Aperf | Avisual | Verdict | 说明 |
|---|---|---|---|---|
| Pass | Pass | Pass | Pass | 一切正常 |
| Pass | Fail | Pass | PerformanceRisk | 功能正确但性能不达标 |
| Pass | Pass | Fail | RenderBug / VisualFail | 渲染表现异常 |
| Fail | Pass | Pass | FunctionalFail | 纯业务功能错误 |
| Fail | Fail | Pass | Mixed | 功能错误 + 性能异常 |
| Fail | Fail | Fail | Mixed / CrashLike | 严重混合故障 |
| Pass | Fail | Fail | Mixed | 结果表面正确，但性能和视觉都异常 |

## 10.3 解释性输出

每次 verdict 不能只给类别，还要给一句解释，例如：

- `FunctionalFail`：接口返回 `2`，页面状态和 OCR 均为 `1`
- `PerformanceRisk`：页面最终正确，但点击到可见变化耗时 1260ms
- `RenderBug`：文本正确，但模板匹配分数过低且模糊度过低
- `Mixed`：页面显示旧数据，同时存在内存告警和明显延迟

这会直接提升答辩时的说服力。

---

## 11. 自动化测试平台设计

## 11.1 开发者工具自动化准备

自动化实践表明，miniprogram-automator 可以与 Jest 搭配；在微信开发者工具中需要开启服务端口，或通过 CLI 启动自动化端口。一个常见流程是：

1. 在开发者工具设置中开启服务端口
2. 使用 `cli auto --project ... --auto-port ...` 启动自动化端口
3. 由 Jest + miniprogram-automator 启动/连接小程序并执行测试 [R5]

## 11.2 测试目录建议

```text
vision-triage/
  demo-uniapp/
  runner/
    tests/
      feed.spec.js
      counter.spec.js
      layout.spec.js
    utils/
      automator.js
      artifact.js
      diagnosis.js
  diagnosis/
    app.py
    diagnose/
      blur.py
      ocr.py
      screen.py
      layout.py
```

## 11.3 每个测试用例的统一流程

1. 调用故障服务：`POST /fault/activate`
2. 启动或连接小程序
3. 进入指定页面
4. 执行动作（点击/刷新/滚动）
5. 等待页面稳定
6. 读取页面状态 JSON
7. 获取文本/元素信息
8. 保存性能指标
9. 截图
10. 调用 `/diagnose`
11. 得到 verdict
12. 保存 artifacts

## 11.4 每次运行必须保存的 artifacts

每个 case 目录下至少保存：

- `case.json`
- `page-state.json`
- `perf.json`
- `screenshot.png`
- `diagnosis.json`
- `console.log`（可选）

## 11.5 Case 定义格式（建议）

```json
{
  "caseId": "counter_slow_api_001",
  "page": "counter",
  "faultProfile": "slow_api",
  "action": "tap_refresh",
  "expected": {
    "verdict": "PerformanceRisk"
  },
  "thresholds": {
    "interactionMs": 800
  }
}
```

---

## 12. Demo 小程序工程设计

## 12.1 推荐目录结构

```text
src/
  pages/
    feed/index.vue
    counter/index.vue
    layout/index.vue
  components/
    FaultPanel.vue
    MetricBadge.vue
  services/
    api.ts
    fault.ts
    perf.ts
    oracle.ts
  stores/
    debug.ts
  utils/
    time.ts
    image.ts
```

## 12.2 各模块职责

### `api.ts`
- 所有接口都从这里出
- 负责把 fault profile 带给后端
- 负责 slow_api / wrong_mapping 这类接口侧故障

### `fault.ts`
- 保存当前 profile
- 暴露统一注入能力
- 不直接和页面耦合

### `perf.ts`
- 采集交互耗时
- 注册 `wx.getPerformance` observer
- 监听 `wx.onMemoryWarning`

### `oracle.ts`
- 汇总页面状态、功能结果、性能结果
- 输出标准 JSON 给自动化层

### `FaultPanel.vue`
- 仅在开发环境或调试包中可见
- 手动切换故障模式
- 自动化环境可绕过 UI，直接调后端

## 12.3 uni-app 条件编译建议

把微信专用埋点全部包在：

```js
// #ifdef MP-WEIXIN
// 微信专用性能采集与开发者工具联动逻辑
// #endif
```

uni-app 官方文档明确支持在 JS/TS、组件、static 目录等位置做 `MP-WEIXIN` 条件编译。[R4]

---

## 13. 开发阶段的调试与注入规则

## 13.1 必须建立统一规则

故障和测试注入不需要做成一个大平台，但必须“统一管理”。  
推荐遵循 4 条规则：

1. **任何故障都必须有名字**
2. **任何注入都只能从统一入口进入**
3. **任何故障都必须能恢复到 normal**
4. **任何 case 都必须落证据**

## 13.2 不允许的做法

- 在页面里随手加散装 `if`
- 测试脚本直接改页面源码
- 每个页面用不同的注入协议
- 调试按钮直接混到正式页面逻辑中

## 13.3 建议的调试方式

### 开发者手动调试
用 `FaultPanel.vue` 直接切 profile

### 自动化调试
runner 先调 `POST /fault/activate`，再执行页面动作

### 结果核对
统一看 case 目录里的截图、状态 JSON、性能 JSON、诊断结果

---

## 14. 里程碑与任务拆解

## 14.1 第一阶段：1 周内完成的最小骨架

- 创建 uni-app vite-ts 工程
- 接入 z-paging
- 完成 `feed` / `counter` / `layout` 三页空壳
- 搭建 FastAPI 服务
- 完成 `fault.ts` / `api.ts` / `perf.ts` 基础框架

## 14.2 第二阶段：2~3 周完成的可跑通原型

- 跑通 `slow_api`
- 跑通 `stale_ui`
- 跑通 `blur_image`
- 接通 miniprogram-automator + Jest
- 自动截图并提交诊断

## 14.3 第三阶段：中期前的可演示版本

- 补 `memory_pressure` / `layout_overlap`
- 完成 OpenCV 模糊与黑白屏判断
- 完成 OCR 文本校验
- 输出 verdict 与 explanation

## 14.4 结题前完善

- 增加 case 数量
- 做对比实验
- 输出误诊率/分诊准确率
- 完成答辩演示录像

---

## 15. 实验设计建议

## 15.1 最小实验集

建议至少准备 8 个样本：

1. `counter + normal`
2. `counter + slow_api`
3. `counter + stale_ui`
4. `counter + mixed_fault`
5. `feed + normal`
6. `feed + blur_image`
7. `feed + slow_api`
8. `layout + layout_overlap`

## 15.2 对比基线

### 基线 A：传统功能测试
只断言数据值和页面文本

### 基线 B：功能 + 性能阈值
不做视觉判断

### 你们的方法：功能 + 性能 + 视觉 + 分诊矩阵

## 15.3 观察指标

- 分诊准确率
- 性能问题误判成功能问题的比例
- 平均定位时间
- 单次测试额外开销（截图/OCR/OpenCV 带来的耗时）

---

## 16. 风险与规避

| 风险 | 表现 | 规避 |
|---|---|---|
| 自动化环境不稳定 | 开发者工具端口连不上 | 优先用本地固定环境，先手动开启端口 |
| uni-app 页面行为与原生小程序不完全一致 | 某些细节不好测 | 把微信专用逻辑放到 MP-WEIXIN 条件编译里 |
| OCR 不稳定 | 小字识别失败 | 只识别固定 ROI，字号放大，减少背景噪声 |
| 视觉误判 | 模板匹配不稳 | 先只做 3 类最稳规则：黑白屏、模糊、OCR |
| 故障注入污染业务代码 | 页面到处是 if | 统一收敛到 fault.ts / api.ts |
| 范围过大 | 做不完 | 只保留 3 页、6 类故障、8 个实验样本 |

---

## 17. 最终推荐落地方案（结论版）

如果只给一句最终建议，那就是：

> **用 uni-app 官方 vite-ts 模板新开一个轻量项目；用 z-paging + 瀑布流组件快速做出 feed / counter / layout 三页；用 miniprogram-automator + Jest 做自动化执行；用 FastAPI 统一管理故障 profile 与诊断 API；用 OpenCV + PaddleOCR 完成视觉断言；把你们真正的创新点放在“证据融合与分诊逻辑”上。**

具体落到项目组合，就是：

- **主工程**：uni-app vite-ts
- **列表页能力**：z-paging
- **图片流能力**：uniapp-waterfalls-flow 或 mp-waterfall
- **自动化**：miniprogram-automator + Jest
- **诊断服务**：FastAPI
- **视觉分析**：OpenCV + PaddleOCR
- **可选增强**：Minium / sentry-miniapp / weixin-devtools-mcp

这样做的最大好处是：

1. **你们真的能做完**
2. **每一层职责清晰**
3. **答辩时容易解释**
4. **实验样本可控**
5. **与开题报告高度一致** [R1]

---

## 18. 附录：建议的仓库与页面命名

### 小程序页面
- `pages/feed/index`
- `pages/counter/index`
- `pages/layout/index`

### 关键组件
- `components/FaultPanel.vue`
- `components/MetricBadge.vue`

### 服务模块
- `services/api.ts`
- `services/fault.ts`
- `services/perf.ts`
- `services/oracle.ts`

### 自动化用例
- `runner/tests/feed.spec.js`
- `runner/tests/counter.spec.js`
- `runner/tests/layout.spec.js`

### Python 模块
- `diagnosis/app.py`
- `diagnosis/diagnose/blur.py`
- `diagnosis/diagnose/ocr.py`
- `diagnosis/diagnose/screen.py`
- `diagnosis/diagnose/layout.py`

---

## 19. 附录：资料来源

下面列出本文写作时重点参考的公开项目与资料。若后续要做开题答辩或论文综述，建议继续把这些项目按“直接采用 / 借鉴 / 对照实验”整理成一页表格。

- R2: https://github.com/dcloudio/uni-app
- R3: https://uniapp.dcloud.net.cn/quickstart-cli.html
- R4: https://uniapp.dcloud.net.cn/tutorial/platform.html
- R5: https://phoenixnest.github.io/MiniProgram-AutoTest/
- R6: https://github.com/leoxiaoge/minium
- R7: https://github.com/mpx-ecology/mpx-e2e
- R8: https://github.com/wechat-miniprogram/miniprogram-simulate
- R9: https://github.com/wooter-s/weixin-devtools-mcp
- R10: https://www.bookstack.cn/read/miniprogram-202505/514ee9970f222118.md
- R11: https://www.bookstack.cn/read/miniprogram-202505/dd492b6fa987afeb.md
- R12: https://www.epoos.com/blog/xcx3/
- R13a: https://docs.opencv.org/4.x/d4/d86/group__imgproc__filter.html
- R13b: https://docs.opencv.org/4.x/de/da9/tutorial_template_matching.html
- R14: https://github.com/PaddlePaddle/PaddleOCR
- R15: https://github.com/dcloudio/hello-uniapp
- R16: https://github.com/codercup/hello-unibest
- R17: https://github.com/SmileZXLee/uni-z-paging
- R18a: https://github.com/deweyou/uniapp-waterfalls-flow
- R18b: https://github.com/zhousihang/uni-waterfall-flow
- R18c: https://github.com/CodingPub/wx-waterfall
- R18d: https://github.com/wittDe/mp-waterfall
- R18e: https://github.com/johanazhu/WeChatMeiZi
- R19: https://github.com/ITxChen/uni-app-vue3-ts
- R20: https://github.com/matrixorigin/matrixone_uniapp_demo
- R21: https://github.com/lizhiyao/sentry-miniapp
- R22: https://github.com/Tencent/FAutoTest
- R23: https://github.com/richshaw2015/wxapp-boot-time


## 20. 附录：与开题报告的一致性说明

本文严格沿用了开题报告中的核心设定：

- 问题定义：功能缺陷与性能瓶颈混淆
- 原型目标：图片流 / 数据更新 / 故障注入 / Python 视觉诊断
- 断言结构：功能断言 + 性能断言 + 视觉断言
- 结果输出：根因分诊与实验验证

但在工程范围上做了收口：

- 删去跨 App 对照的第一版要求
- 不把“自动生成预言代码”作为主目标
- 先完成规则法分诊，再考虑更复杂的自适应阈值与模板生成
