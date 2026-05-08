# Vision-Triage 开发日志

## 2025-04-20 项目初始化 - 阶段一完成

### 完成事项

- 创建项目目录结构和文档规范
- 搭建 uni-app Vue3+TS 小程序工程（官方 vite-ts 模板）
- 实现 3 个 Demo 页面：
  - `pages/feed/index.vue` - 图片流（瀑布流、模糊、白屏场景）
  - `pages/counter/index.vue` - 数据更新（旧值、映射错误场景）
  - `pages/layout/index.vue` - 布局压力（错位、重叠、溢出场景）
- 实现 services 层：
  - `fault.ts` - 8种故障 profile 状态管理
  - `api.ts` - 统一请求层，带 fault profile header
  - `perf.ts` - 性能指标采集（交互耗时、内存告警、wx.getPerformance）
  - `oracle.ts` - 页面状态导出协议
- 实现 FaultPanel 调试组件（浮动面板，可切换故障模式）
- 搭建 FastAPI 诊断服务后端（端口 8900）：
  - Mock API: /api/feed, /api/counter, /api/layout
  - 故障控制: /fault/activate, /fault/status
  - 诊断入口: /diagnose
- 实现视觉诊断模块并通过单元测试：
  - `blur.py` - Laplacian 方差模糊检测
  - `screen.py` - 黑/白屏检测
  - `ocr.py` - PaddleOCR 文字提取与验证
  - `layout.py` - 模板匹配与重叠检测
  - `triage.py` - 三重断言分诊决策引擎

### 验证结果

- uni-app 编译到 mp-weixin 成功（26个文件输出）
- H5 开发服务器正常运行（localhost:5173）
- FastAPI 所有 API 端点正常响应
- 分诊测试全部通过：
  - Pass（正常） ✓
  - PerformanceRisk（性能超标） ✓
  - FunctionalFail（功能错误） ✓
  - RenderBug（视觉异常） ✓
  - Mixed（混合故障） ✓

### 项目结构

```text
d:\weixinmp_test\
├── docs/                     # 项目文档
│   ├── plan.md
│   ├── todo.md
│   └── docrules.md
├── demo-uniapp/              # uni-app 小程序
│   ├── src/
│   │   ├── pages/feed/       # 图片流页
│   │   ├── pages/counter/    # 数据更新页
│   │   ├── pages/layout/     # 布局压力页
│   │   ├── components/       # FaultPanel
│   │   └── services/         # api/fault/perf/oracle
│   ├── dist/build/mp-weixin/ # 编译输出
│   └── package.json
├── diagnosis/                # Python 诊断服务
│   ├── app.py               # FastAPI 主入口
│   ├── diagnose/            # 诊断模块
│   └── requirements.txt
└── README.md
```

---

## 2025-04-20 测试用例集构建与验证

### 完成事项

- 构建 5 个测试套件、76 个测试用例
- 全部通过（100% pass rate，耗时 3.2s）

### 测试覆盖

| 套件 | 数量 | 验证内容 |
|------|------|---------|
| test_blur | 12 | 模糊检测准确性（清晰/重度/轻度/文字/噪声/单调性） |
| test_screen | 12 | 黑白屏检测（纯色/比例边界/暗色UI/浅色UI/状态栏） |
| test_layout | 11 | 模板匹配（精确/位置/遮挡/缩放）+ 重叠检测 |
| test_triage | 24 | 分诊决策矩阵全覆盖 + 边界条件 + 解释质量 |
| test_api | 17 | API端点集成（故障管理/Feed/Counter/Layout/诊断） |

### 发现并修复的 Bug

1. **`screen.py` 边界条件** — `black_ratio > ratio` 改为 `>=`，边界值应归入异常侧
2. **`app.py` Form 参数声明** — `/diagnose` 端点的 `page_state`/`perf_data` 需要 `Form()` 声明，否则 multipart 请求中无法解析
3. **模板匹配测试** — 纯色背景导致 matchTemplate 退化，改用随机纹理背景

### 下一步

- 用微信开发者工具导入并实机调试
- 接入 miniprogram-automator + Jest 自动化
- 完善 OCR 功能验证流程
