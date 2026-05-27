# 陌生小程序零侵入 driver 报告 @ 20260527_021146

- project: `D:/weixinmp_test/third-youzouzou-wxapp`
- 页面数: 2 | 成功诊断: 0 | attach 成功率: 0%
- **健康页假阳率** — verdict(主): None | baseline: None | webug: None | 任一通道: None
- Qwen 视觉 oracle: True

> 说明：独立第三方小程序不调用本项目故障后端，无法零侵入注入故障；本报告验证的是**零集成 attach + 真实页面多通道诊断 + 健康页假阳率**（分通道），不是故障检出率。

| page | verdict | baseline_ssim | verdict_fp | baseline_fp | webug_fp |
|---|---|---|---|---|---|
| others | CAPTURE_FAIL | — | — | — | — |
| example | CAPTURE_FAIL | — | — | — | — |