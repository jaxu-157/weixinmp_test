# Vision-Triage 项目开发计划

## 项目概述
基于"功能断言+性能断言+视觉断言"的微信小程序故障分诊原型。

## 架构
```
三层架构：
1. uni-app Demo 小程序（Vue3 + TypeScript）
2. Node 自动化执行层（Jest + miniprogram-automator）
3. Python 诊断与注入层（FastAPI + OpenCV + PaddleOCR）
```

## 开发阶段

### 阶段一：最小骨架（当前）
- [x] 创建项目结构与文档
- [x] 搭建 uni-app vite-ts 工程
- [x] 完成 feed / counter / layout 三页
- [x] 搭建 FastAPI 服务
- [x] 完成 fault.ts / api.ts / perf.ts / oracle.ts

### 阶段二：可跑通原型
- [ ] 跑通 slow_api 故障
- [ ] 跑通 stale_ui 故障
- [ ] 跑通 blur_image 故障
- [ ] 接通 miniprogram-automator + Jest
- [ ] 自动截图并提交诊断

### 阶段三：可演示版本
- [ ] 补 memory_pressure / layout_overlap
- [ ] 完成 OpenCV 模糊与黑白屏判断
- [ ] 完成 OCR 文本校验
- [ ] 输出 verdict 与 explanation

### 阶段四：结题完善
- [ ] 增加 case 数量
- [ ] 做对比实验
- [ ] 输出误诊率/分诊准确率

## 技术栈
| 层级 | 技术 |
|---|---|
| 小程序 | uni-app + Vue3 + TypeScript |
| UI组件 | uni-ui + z-paging |
| 自动化 | miniprogram-automator + Jest |
| 后端 | FastAPI (Python 3.11) |
| 视觉分析 | OpenCV + PaddleOCR |
