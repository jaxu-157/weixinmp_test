"""故障交互分析。

从检测矩阵中计算故障间的影响关系：
  - Masking（掩盖）: 注入 A → B 的检出率下降（A 压住了 B 的信号）
  - Excitation（激发）: 注入 A → B 的检测器误报（A 触发了 B 的假阳性）
  - Independence（独立）: 两者互不影响

核心公式（贝叶斯条件概率）：
  masking_strength(A→B) = P(B_det | B_inj, A_not_inj) - P(B_det | B_inj, A_inj)
  excitation_strength(A→B) = P(B_det | B_not_inj, A_inj) - P(B_det | B_not_inj, A_not_inj)

  值域 [-1, 1]，正 = A 压抑 B（masking），正 = A 激发 B 假阳性（excitation）
  绝对值 > 阈值 = 显著交互
"""
from mitrix.engine import ATOMIC_FAULTS

# 显著交互阈值
MASKING_THRESHOLD = 0.3    # 检出率下降超过 30% 才算掩盖
EXCITATION_THRESHOLD = 0.3

# 最少样本数
MIN_SAMPLES = 1


def analyze(results: list[dict]) -> dict:
    """分析所有故障对之间的交互关系。

    Args:
        results: runner 的完整结果列表，每项含 oracle, detected

    Returns:
        {
            "pairs": [
                {
                    "from": "wrong_mapping",
                    "to": "stale_ui",
                    "type": "masking",
                    "strength": 1.0,
                    "evidence": "P(stale_ui|stale_ui_inj, wrong_mapping_not) = 1.00
                                 P(stale_ui|stale_ui_inj, wrong_mapping_inj) = 0.00
                                 → stale_ui 检出率因 wrong_mapping 下降 1.00",
                },
                ...
            ],
            "excitation_pairs": [...],
            "masking_pairs": [...],
            "summary": "发现 1 组掩盖、0 组激发",
        }
    """
    # 按 oracle 分组统计：key = (A_inj, B_inj, A_det, B_det)
    # 实际做法：遍历所有 case，按 (A_inj, B_inj) 建组，统计 B_det 的均值

    pairs = []

    for a in ATOMIC_FAULTS:
        for b in ATOMIC_FAULTS:
            if a == b:
                continue
            masking, excit, evidence = _analyze_pair(results, a, b)
            if masking is not None:
                pairs.append(masking)
            if excit is not None:
                pairs.append(excit)

    masking_pairs = [p for p in pairs if p["type"] == "masking"]
    excitation_pairs = [p for p in pairs if p["type"] == "excitation"]

    # 排序
    pairs.sort(key=lambda p: -p["strength"])

    summary_parts = []
    if masking_pairs:
        summary_parts.append(f"{len(masking_pairs)} 组掩盖")
    if excitation_pairs:
        summary_parts.append(f"{len(excitation_pairs)} 组激发")
    if not summary_parts:
        summary_parts.append("无显著交互")

    return {
        "pairs": pairs,
        "masking_pairs": masking_pairs,
        "excitation_pairs": excitation_pairs,
        "summary": "、".join(summary_parts),
    }


def _analyze_pair(results: list[dict], a: str, b: str) -> tuple:
    """分析 A→B 的单向交互。

    Returns:
        (masking_dict or None, excitation_dict or None, evidence_str)
    """
    # 四组数据
    # Group 00: A=0, B=0
    # Group 01: A=0, B=1
    # Group 10: A=1, B=0
    # Group 11: A=1, B=1

    groups = {"00": [], "01": [], "10": [], "11": []}
    for case in results:
        oracle = case.get("oracle", {})
        detected = case.get("detected", {})
        if not oracle or not detected:
            continue
        a_inj = 1 if oracle.get(a, False) else 0
        b_inj = 1 if oracle.get(b, False) else 0
        b_det = detected.get(b, 0)
        key = f"{a_inj}{b_inj}"
        groups[key].append(b_det)

    masking = None
    excitation = None

    # ---- Masking: B injected (B=1), compare A=0 vs A=1 ----
    group_01 = groups.get("01", [])
    group_11 = groups.get("11", [])

    if len(group_01) >= MIN_SAMPLES and len(group_11) >= MIN_SAMPLES:
        rate_b_alone = sum(group_01) / len(group_01)   # P(B_det | B_inj, A_not)
        rate_b_with_a = sum(group_11) / len(group_11)  # P(B_det | B_inj, A_inj)
        strength = rate_b_alone - rate_b_with_a         # 正值 = A 掩盖了 B

        if abs(strength) >= MASKING_THRESHOLD:
            label = "masking" if strength > 0 else "amplification"
            masking = {
                "from": a,
                "to": b,
                "type": label,
                "strength": round(strength, 3),
                "evidence": (
                    f"P({b}|{b}_inj, {a}_not) = {rate_b_alone:.2f} "
                    f"vs P({b}|{b}_inj, {a}_inj) = {rate_b_with_a:.2f} "
                    f"→ {b} 检出率因 {a} {'下降' if strength > 0 else '上升'} {abs(strength):.2f}"
                ),
            }

    # ---- Excitation: B NOT injected (B=0), compare A=0 vs A=1 ----
    group_00 = groups.get("00", [])
    group_10 = groups.get("10", [])

    if len(group_00) >= MIN_SAMPLES and len(group_10) >= MIN_SAMPLES:
        rate_no_b = sum(group_00) / len(group_00)       # P(B_det | B_not, A_not)
        rate_b_false = sum(group_10) / len(group_10)     # P(B_det | B_not, A_inj)
        strength = rate_b_false - rate_no_b              # 正值 = A 激发了 B 的假阳性

        if abs(strength) >= EXCITATION_THRESHOLD:
            excitation = {
                "from": a,
                "to": b,
                "type": "excitation",
                "strength": round(strength, 3),
                "evidence": (
                    f"P({b}|{b}_not, {a}_not) = {rate_no_b:.2f} "
                    f"vs P({b}|{b}_not, {a}_inj) = {rate_b_false:.2f} "
                    f"→ {b} 假阳性率因 {a} {'上升' if strength > 0 else '下降'} {abs(strength):.2f}"
                ),
            }

    return masking, excitation, None


def format_interaction_report(analysis: dict) -> str:
    """格式化交互分析为可读文本。"""
    lines = []
    lines.append("=" * 70)
    lines.append("  故障交互分析 (Fault Interaction Analysis)")
    lines.append("=" * 70)
    lines.append(f"结论: {analysis['summary']}")
    lines.append("")

    if analysis["masking_pairs"]:
        lines.append("── 掩盖关系 (Masking) ──")
        lines.append("  A 注入后 B 的检出率显著下降，A 压住了 B 的信号。")
        lines.append("")
        for p in analysis["masking_pairs"]:
            arrow = "──→"
            lines.append(f"  {p['from']:<20s} {arrow} mask {p['to']:<20s}  strength={p['strength']:.3f}")
            lines.append(f"    {p['evidence']}")
            lines.append("")

    if analysis["excitation_pairs"]:
        lines.append("── 激发关系 (Excitation) ──")
        lines.append("  A 注入后 B 的检测器假阳性率显著上升。")
        lines.append("")
        for p in analysis["excitation_pairs"]:
            arrow = "──→"
            lines.append(f"  {p['from']:<20s} {arrow} excite {p['to']:<20s}  strength={p['strength']:.3f}")
            lines.append(f"    {p['evidence']}")
            lines.append("")

    if not analysis["masking_pairs"] and not analysis["excitation_pairs"]:
        lines.append("  所有故障对之间无显著交互，检测器相互独立。")

    lines.append("")
    lines.append("  解读:")
    lines.append("    masking:     修 A 的 bug 可能让 B 的检出率恢复")
    lines.append("    excitation:  A 的检测器太宽，修 A 的检测器会减少 B 的假阳性")
    lines.append("    amplification: A 注入反而增强了 B 的信号")
    return "\n".join(lines)


# ================================================================
# API: 直接对 runner 结果运行
# ================================================================

def run_on_report(report_path: str) -> dict:
    """对已有的 mitrix JSON 报告运行交互分析。"""
    import json
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)
    results = report.get("results", [])
    if not results:
        print("报告无结果数据")
        return {}
    analysis = analyze(results)
    print(format_interaction_report(analysis))
    return analysis


if __name__ == "__main__":
    import sys
    import os
    # 默认分析最新报告
    reports_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
    reports = sorted(
        [f for f in os.listdir(reports_dir) if f.startswith("mitrix_report_") and f.endswith(".json")],
        reverse=True,
    )
    if reports:
        run_on_report(os.path.join(reports_dir, reports[0]))
    else:
        print("未找到 mitrix 报告")
