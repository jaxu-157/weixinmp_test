"""扫描 packages/sample-apps/ 下所有样例小程序，量化 Vision-Triage SDK 的集成成本。

输出：
- 每个样例的 (集成行数, 业务行数, 集成占比)
- 一份机器可读的 JSON
- 一张柱状图：业务 vs 集成 LOC 对比

定义：
- "集成 LOC" = 任一行包含以下任一关键词：
    vision-triage-sdk, installTriage, useTriageProbe, probe.,
    activateFault, syncFromServer, getFaultState, markInteraction, markPageLoad
- "业务 LOC" = 非空、非纯注释、非纯样式的行 - 集成 LOC
"""
from __future__ import annotations

import os
import json
import re
import sys
import argparse
from typing import List, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


SAMPLE_APPS_DIR = os.path.dirname(os.path.abspath(__file__))

INTEGRATION_PATTERNS = re.compile(
    r"(vision-triage-sdk|installTriage|useTriageProbe|probe\.|"
    r"activateFault|syncFromServer|getFaultState|markInteraction|markPageLoad)"
)

CODE_EXTENSIONS = {".ts", ".vue", ".js"}


def _strip_style_block(content: str) -> str:
    """从 .vue 文件里去掉 <style> 块（不计入业务 LOC）。"""
    return re.sub(r"<style[^>]*>[\s\S]*?</style>", "", content)


def _is_meaningful_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if s.startswith("//") or s.startswith("/*") or s.startswith("*"):
        return False
    if s in ("{", "}", "[", "]", "(", ")"):
        return False
    return True


def count_loc(path: str) -> Tuple[int, int]:
    """返回 (integration_loc, business_loc)。"""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if path.endswith(".vue"):
        content = _strip_style_block(content)

    integration = 0
    meaningful = 0
    for raw in content.split("\n"):
        if not _is_meaningful_line(raw):
            continue
        meaningful += 1
        if INTEGRATION_PATTERNS.search(raw):
            integration += 1

    business = max(0, meaningful - integration)
    return integration, business


def audit_app(app_dir: str) -> dict:
    name = os.path.basename(app_dir.rstrip(os.sep))
    files = []
    int_total = 0
    biz_total = 0
    n_pages = 0

    for root, _dirs, fnames in os.walk(os.path.join(app_dir, "src")):
        for fn in fnames:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in CODE_EXTENSIONS:
                continue
            full = os.path.join(root, fn)
            integ, biz = count_loc(full)
            int_total += integ
            biz_total += biz
            files.append({
                "file": os.path.relpath(full, app_dir).replace("\\", "/"),
                "integration_loc": integ,
                "business_loc": biz,
            })
            if "pages" in full and fn.endswith(".vue"):
                n_pages += 1

    total_loc = int_total + biz_total
    integ_ratio = (int_total / total_loc) if total_loc else 0.0
    return {
        "app": name,
        "n_pages": n_pages,
        "integration_loc": int_total,
        "business_loc": biz_total,
        "total_loc": total_loc,
        "integration_ratio": round(integ_ratio, 4),
        "files": files,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=str,
                        default=os.path.join(SAMPLE_APPS_DIR, "integration_audit.json"))
    args = parser.parse_args()

    apps = []
    for entry in sorted(os.listdir(SAMPLE_APPS_DIR)):
        full = os.path.join(SAMPLE_APPS_DIR, entry)
        if not os.path.isdir(full):
            continue
        if not os.path.exists(os.path.join(full, "src")):
            continue
        apps.append(audit_app(full))

    # 汇总
    total_integ = sum(a["integration_loc"] for a in apps)
    total_biz = sum(a["business_loc"] for a in apps)
    total_pages = sum(a["n_pages"] for a in apps)

    print(f"\n{'app':<22}{'pages':<8}{'integ_loc':<12}{'biz_loc':<12}{'integ%':<10}")
    print("-" * 70)
    for a in apps:
        print(f"{a['app']:<22}{a['n_pages']:<8}{a['integration_loc']:<12}"
              f"{a['business_loc']:<12}{a['integration_ratio']:<10.2%}")
    print("-" * 70)
    overall_ratio = total_integ / (total_integ + total_biz) if (total_integ + total_biz) else 0
    print(f"{'TOTAL':<22}{total_pages:<8}{total_integ:<12}{total_biz:<12}{overall_ratio:<10.2%}")

    summary = {
        "apps": apps,
        "summary": {
            "n_apps": len(apps),
            "total_pages": total_pages,
            "total_integration_loc": total_integ,
            "total_business_loc": total_biz,
            "overall_integration_ratio": overall_ratio,
        },
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"\nJSON: {args.out}")

    # 柱状图
    fig, ax = plt.subplots(figsize=(8, 5))
    names = [a["app"] for a in apps]
    x = range(len(names))
    biz = [a["business_loc"] for a in apps]
    integ = [a["integration_loc"] for a in apps]
    ax.bar(x, biz, label="business LOC", color="#4A90D9")
    ax.bar(x, integ, bottom=biz, label="integration LOC", color="#e74c3c")
    ax.set_xticks(list(x))
    ax.set_xticklabels(names, rotation=15)
    ax.set_ylabel("Lines of code")
    ax.set_title("Vision-Triage SDK Integration Cost Across Sample Apps")
    for i, a in enumerate(apps):
        ax.text(i, biz[i] + integ[i] + 1,
                f"{a['integration_ratio']:.1%}",
                ha="center", fontsize=9)
    ax.legend()
    plt.tight_layout()
    png_path = os.path.join(SAMPLE_APPS_DIR, "integration_audit.png")
    fig.savefig(png_path, dpi=140)
    plt.close(fig)
    print(f"PNG: {png_path}")


if __name__ == "__main__":
    main()
