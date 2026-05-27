# 陌生小程序零侵入 driver 报告 @ 20260527_021955

- project: `D:/weixinmp_test/third-youzouzou-wxapp`
- 页面数: 2 | 成功诊断: 2 | attach 成功率: 100%
- **健康页假阳率** — verdict(主): 1.0 | baseline: 0.0 | webug: 0.0 | 任一通道: 1.0
- Qwen 视觉 oracle: True

> 说明：独立第三方小程序不调用本项目故障后端，无法零侵入注入故障；本报告验证的是**零集成 attach + 真实页面多通道诊断 + 健康页假阳率**（分通道），不是故障检出率。

| page | verdict | baseline_ssim | verdict_fp | baseline_fp | webug_fp |
|---|---|---|---|---|---|
| others | RenderBug | 1.0 | 是 | 否 | 否 |
| example | RenderBug | 1.0 | 是 | 否 | 否 |