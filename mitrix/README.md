# mitrix — 组合故障注入 × 多标签诊断

## 概述

mitrix 是 Vision-Triage 项目的技术创新模块，核心思路：

1. **组合故障注入** — 不只测 8 个固定 profile，而是自动生成单故障 + 两两组合 + 三故障组合的测试用例
2. **声明式多标签诊断** — 每个原子故障定义自己的"信号签名"，引擎在断言空间中独立匹配，输出 6-bit 检测向量
3. **故障检测矩阵** — 行 = 测试用例，列 = 原子故障，单元格 = detected / not，附带每故障 Precision / Recall / F1
4. **故障交互分析** — 从矩阵中自动挖掘故障间因果关系：掩盖（masking）、激发（excitation）、独立（independence）

## 前置条件

1. **微信开发者工具**已打开，并导入了小程序项目
   - 项目路径：`demo-uniapp/dist/build/mp-weixin`
   - AppID：`wx90551d59d41885eb`

2. **Conda 环境**：`vision-triage`（已安装 minium, fastapi, opencv 等）

3. **小程序已编译**（改过前端代码后需要重新编译）：
   ```bash
   cd demo-uniapp && npx uni build -p mp-weixin && cd ..
   ```

## 一键运行

```bash
conda activate vision-triage
python run_mitrix_test.py
```

约 2 分钟完成 17 个用例，输出到终端 + `reports/` 目录。

### 可选参数

```bash
python run_mitrix_test.py --generate-only    # 仅生成用例 JSON，不执行测试
python run_mitrix_test.py --single-only      # 仅测试 6 个单故障
python run_mitrix_test.py --pairs-only       # 仅测试两两组合
python run_mitrix_test.py --cases <文件>     # 使用自定义用例 JSON
```

## 流程

```
┌──────────────────────────────────────────────────────────────────┐
│                     run_mitrix_test.py                           │
├──────────────────────────────────────────────────────────────────┤
│  1. 启动后端 (uvicorn app:app --port 8900)                       │
│  2. generator.py → 自动生成 17 个测试用例 → mitrix_test_cases.json │
│  3. 连接微信开发者工具 (minium)                                    │
│  4. 逐用例执行 (runner.py)：                                      │
│     ┌─────────────────────────────────────────┐                  │
│     │ a. POST /fault/activate-multi           │ ← 激活组合故障    │
│     │    {"profiles": ["blur_image","slow_api"]}│                  │
│     │                                         │                  │
│     │ b. mini.app.relaunch("/pages/feed/index")│ ← 导航到页面     │
│     │                                         │                  │
│     │ c. mini.app.screen_shot()               │ ← 截图           │
│     │                                         │                  │
│     │ d. POST /diagnose                       │ ← 提交截图+数据   │
│     │    (screenshot + page_state + perf_data) │                  │
│     │                                         │                  │
│     │ e. engine.detect_all()                  │ ← 多标签检测      │
│     │    匹配 SIGNATURES 中每条故障的声明式签名  │                  │
│     │    输出 6-bit 检测向量                    │                  │
│     │                                         │                  │
│     │ f. oracle 比对 → 记录 match_vec          │                  │
│     └─────────────────────────────────────────┘                  │
│  5. 生成故障检测矩阵 + 每故障 F1 指标                              │
│  6. 重置故障为 normal，关闭后端                                    │
└──────────────────────────────────────────────────────────────────┘
```

## 文件结构

```
mitrix/
├── README.md          ← 本文件
├── __init__.py
├── generator.py       ← 测试用例生成器（组合 + 页面选择 + oracle）
├── engine.py          ← 声明式多标签诊断引擎（信号签名匹配）
├── interaction.py     ← 故障交互分析（掩盖 / 激发检测）
├── runner.py          ← 编排器（激活→截图→诊断→矩阵→交互分析）
└── win_capture.py     ← Windows 截图兜底

run_mitrix_test.py     ← 入口脚本（一键启动）
mitrix_test_cases.json ← 自动生成的用例 JSON
```

## 输出

每次运行在 `reports/` 下生成：

- `mitrix_report_{时间戳}.json` — 完整数据（17 个用例的 oracle、detected、confidence、match_vec、metrics）
- `mitrix_matrix_{时间戳}.txt` — 可读矩阵 + 每故障 F1 + 交互分析
- `screenshots/mitrix_*.png` — 17 张截图

## 与原测试的关系

| | run_auto_test.py | run_mitrix_test.py |
|---|---|---|
| 测试对象 | 8 个固定 profile | 自动生成的组合用例 |
| 用例数 | 14 | 17 |
| 判决方式 | 单一 verdict (5 类) | 多标签向量 (6-bit) |
| 输出 | Pass/Fail 矩阵 | 检测矩阵 + F1 + 交互分析 |
| 后端 | /fault/activate | /fault/activate-multi |

两者互不影响，独立运行。后端新增的 `/fault/activate-multi` 端点不影响原有 `/fault/activate`，`fault.ts` 的 `split('+')` 对单 profile 向后兼容。

## 声明式签名系统

新增故障只需在 `engine.py` 的 `SIGNATURES` 字典中添加一条，无需写检测函数：

```python
SIGNATURES = {
    "blur_image": (
        ["feed"],                                       # 适用页面
        [                                              # 信号模式列表
            ("visual.is_blur",    "eq", True,     0.90),
            ("visual.blur_score", "lt", 200.0,    0.70),
        ],
        "any",                                          # any=任一命中即检出
    ),
    "stale_ui": (
        ["counter"],
        [("functional.reason", "regex", r"visible=(\d+)", 0.85)],
        "any",
    ),
    # ...
}
```

每条规则 = `(断言路径, 操作符, 期望值, 置信度)`，操作符支持 eq/neq/gt/lt/contains/regex。

## 故障交互分析

每次测试结束后自动分析故障间的因果关系。对每一对故障 (A, B)，将全部用例按 oracle 分成四组 `(A_inj, B_inj) ∈ {00, 01, 10, 11}`，计算条件概率：

| 交互类型 | 检测条件 | 含义 |
|---|---|---|
| **Masking**（掩盖） | P(B_det \| B_inj, A_not) − P(B_det \| B_inj, A_inj) > 0.3 | A 注入后 B 的检出率显著下降 |
| **Excitation**（激发） | P(B_det \| B_not, A_inj) − P(B_det \| B_not, A_not) > 0.3 | A 注入后 B 的假阳性率上升 |

当前分析结论（基于 17 个用例）：

```
wrong_mapping ──→ mask stale_ui   strength=1.000
  P(stale_ui | stale_inj, wrong_not) = 1.00
  P(stale_ui | stale_inj, wrong_inj) = 0.00
```

wrong_mapping 把 API 字段 `value` 改名 `val`，导致 stale_ui 的值完全不可见。

也可以对已有报告单独运行：

```bash
python -m mitrix.interaction
```
