"""陌生（真正独立的）开源小程序 —— 零侵入 driver 验证 runner。

与 run_real_matrix.py 的关键区别（也是诚实的能力边界）：
  - run_real_matrix.py 依赖本项目的 FastAPI 故障后端 activate_fault()，只对
    "集成了本项目故障 hook 的小程序"（demo-uniapp / 其再皮肤化副本）有效。
  - 真正独立的第三方小程序（如 Tencent/tdesign-retail、lin-xin/wxapp-mall）**不调用本后端**，
    且小程序运行时是沙箱（无 DOM/CSS 注入、本地 mock 数据无 wx.request 可拦截）——
    因此**无法零侵入地注入 8 类故障**。这是真实限制，不掩盖。

那么对独立小程序，零侵入 driver 能诚实验证的是：
  1. **能否 0 行集成地 attach 上去**（Minium 指向编译产物即可）。
  2. **能否遍历它的真实页面并跑通三/四通道诊断**（learned verdict / baseline / webug / Qwen 视觉 oracle）。
  3. **健康页面上的假阳率**（healthy 页面被误判为非 Pass 的比例）——这是工程可用性的关键指标，
     越低说明 driver 越不会在正常小程序上"乱报"。

用法：
    python run_foreign_matrix.py --project D:\\weixinmp_test\\third-wxapp-mall --tag wxapp
    python run_foreign_matrix.py --project D:\\weixinmp_test\\third-tdesign-retail --tag tdesign --qwen
    # 页面默认从 app.json 的 tabBar 自动读取；也可 --pages /a/b,/c/d 手动指定
前置：
    - 微信开发者工具已开、已开启 CLI/服务端口；tdesign 需先 npm install 并在工具里"构建 npm"。
    - project.config.json 的 appid 必须有效（两个候选都已是有效 appid）。
"""
from __future__ import annotations

import os
import sys
import json
import time
import shutil
import argparse
import traceback
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
AUTO_TEST_DIR = os.path.abspath(os.path.join(HERE, ".."))
REPO_ROOT = os.path.dirname(AUTO_TEST_DIR)
for p in (HERE, AUTO_TEST_DIR, REPO_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from config import TEST_CONFIG  # type: ignore  # noqa: E402
from driver_engine import DriverEngine  # type: ignore  # noqa: E402
from stability_wait import wait_from_files  # type: ignore  # noqa: E402


def tabbar_pages_from_appjson(project_path: str) -> list:
    """从小程序 app.json 读 tabBar 页面路径（带前导 /，可直接 switch_tab）。

    若无 tabBar，则退回取 pages 前 4 个。返回 [(name, "/path"), ...]。
    """
    app_json = os.path.join(project_path, "app.json")
    if not os.path.exists(app_json):
        # 编译产物里可能是 app.json 在子目录；尽力找一个
        for root, _dirs, files in os.walk(project_path):
            if "app.json" in files:
                app_json = os.path.join(root, "app.json")
                break
    with open(app_json, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    raw = []
    tabbar = cfg.get("tabBar", {})
    if tabbar.get("list"):
        raw = [it["pagePath"] for it in tabbar["list"]]
    else:
        raw = cfg.get("pages", [])[:4]

    out = []
    for p in raw:
        path = p if p.startswith("/") else "/" + p
        # name 取倒数第二段或第一段，尽量可读
        seg = [s for s in path.split("/") if s]
        name = seg[-2] if len(seg) >= 2 and seg[-1] in ("index", "home") else seg[-1]
        out.append((name, path))
    return out


def page_type_of(name: str) -> str:
    """把陌生页面名映射到 learned_triage 认识的 page_type（影响视觉 ROI）。"""
    n = name.lower()
    if any(k in n for k in ("home", "index", "category", "list", "goods", "feed")):
        return "feed"     # 图片密集页
    if any(k in n for k in ("cart", "user", "usercenter", "order", "person")):
        return "counter"  # 文字/数字页
    return "feed"


def _switch(app, path):
    try:
        app.switch_tab(path)
    except Exception:
        app.navigate_to(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, help="独立小程序编译产物目录（含 app.json）")
    ap.add_argument("--tag", default="foreign", help="输出文件前缀")
    ap.add_argument("--pages", default=None, help="手动页面列表，逗号分隔，如 /pages/home/home,/pages/cart/index")
    ap.add_argument("--qwen", action="store_true", help="视觉 oracle 启用 rule→Qwen cascade（需 DASHSCOPE_API_KEY/qwen.md）")
    ap.add_argument("--repeat", type=int, default=2, help="每页采集次数（≥2 用于测 baseline 自一致性/假阳）")
    ap.add_argument("--connect", action="store_true",
                    help="连接已手动打开的 devtools（不 relaunch）。"
                         "用于规避 minium 已知问题：Minium 自己 relaunch 的 devtools 第二次起 screen_shot 不写文件；"
                         "手动开着前台 devtools 并加载好本项目时用此模式最稳。")
    args = ap.parse_args()

    TEST_CONFIG["project_path"] = args.project
    TEST_CONFIG["appid"] = ""  # 让 minium 从 project.config.json 读
    if args.connect:
        TEST_CONFIG["auto_relaunch"] = False  # 连已开实例，别重启（保住能截图的前台会话）

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(AUTO_TEST_DIR, "reports", "v2_driver", f"{args.tag}_foreign_{ts}")
    shot_dir = os.path.join(out_dir, "screenshots")
    diff_dir = os.path.join(out_dir, "diffs")
    baseline_dir = os.path.join(AUTO_TEST_DIR, f"v2_baselines_{args.tag}")
    for d in (shot_dir, diff_dir, baseline_dir):
        os.makedirs(d, exist_ok=True)

    if args.pages:
        pages = []
        for p in args.pages.split(","):
            p = p.strip()
            seg = [s for s in p.split("/") if s]
            pages.append((seg[-1] if seg else p, p))
    else:
        pages = tabbar_pages_from_appjson(args.project)
    print(f"[foreign] project={args.project}")
    print(f"[foreign] pages={pages}")
    print(f"[foreign] qwen_oracle={args.qwen}\n")

    engine = DriverEngine(baseline_dir=baseline_dir, use_learned=True, use_cascade=args.qwen)

    print("[foreign] launching minium ...")
    import minium
    mini = minium.Minium(TEST_CONFIG)
    print("[foreign] minium ready\n")

    tmp_dir = os.path.join(shot_dir, "_probe")
    os.makedirs(tmp_dir, exist_ok=True)
    results = []

    # 预热：relaunch 后模拟器需时间渲染，否则首次 screen_shot 偶发不写文件（已知 minium flaky）。
    # 先切到首页、等渲染、丢弃式截图把通道"焐热"，失败不计。
    if pages:
        try:
            _switch(mini.app, pages[0][1])
        except Exception:
            pass
        time.sleep(8.0)
        for _ in range(3):
            try:
                mini.app.screen_shot(os.path.join(tmp_dir, "_warmup.png"))
            except Exception:
                pass
            time.sleep(1.5)
        print("[foreign] warmup done\n")

    try:
        for name, path in pages:
            ptype = page_type_of(name)
            shots = []
            for rep in range(args.repeat):
                _switch(mini.app, path)
                time.sleep(0.5)

                def take_to(p, _app=mini.app):
                    _app.screen_shot(p)

                try:
                    stable_path, trace = wait_from_files(
                        take_to, tmp_dir, max_wait_ms=5000, poll_interval_ms=250,
                        ssim_threshold=0.985, stable_window=3,
                    )
                except Exception as e:
                    print(f"  [{name}] capture rep{rep} ERROR: {e}")
                    continue
                dst = os.path.join(shot_dir, f"{name}_rep{rep}.png")
                shutil.copy2(stable_path, dst)
                shots.append((dst, trace))

            if not shots:
                results.append({"page": name, "path": path, "verdict": "CAPTURE_FAIL"})
                continue

            # 第一帧建基线；最后一帧做诊断。基线 key 必须与 diagnose 的 page 参数一致（都用 ptype），
            # 否则 baseline_store 查不到（之前的 ssim=None bug）。save+diagnose 逐页相邻，ptype 复用不冲突。
            engine.force_save_baseline(ptype, shots[0][0])
            diag_path, trace = shots[-1]
            r = engine.diagnose(
                page=ptype, profile="unknown",
                screenshot_path=diag_path,
                perf={"interaction_ms": trace.wait_ms, "memory_warnings": 0},
                business={},  # 独立 app 无 ground-truth 业务值
                diff_out_dir=diff_dir,
            )
            bd = r.baseline_diff or {}
            wb = r.webug
            # 分通道记假阳（健康页面上任何"异常"都是假阳）：
            verdict_fp = (r.verdict != "Pass")                      # 主输出：五分类 verdict
            baseline_fp = bool(bd.get("ssim", 1.0) < 0.92)          # 辅助：与自身基线回归（页面自一致性）
            webug_fp = any(wb.get(k) for k in ("r1_api_timeout_no_feedback", "r2_layout_overflow", "r3_async_data_mismatch"))
            any_fp = verdict_fp or baseline_fp or webug_fp
            results.append({
                "page": name, "path": path, "page_type": ptype,
                "verdict": r.verdict, "engine": r.engine,
                "baseline_ssim": bd.get("ssim"),
                "verdict_fp": verdict_fp,
                "baseline_fp": baseline_fp,
                "webug_fp": webug_fp,
                "false_positive": any_fp,
                "stability_ms": trace.wait_ms,
                "evidence": r.evidence,
            })
            tags = [t for t, v in (("verdict", verdict_fp), ("baseline", baseline_fp), ("webug", webug_fp)) if v]
            print(f"  [{name:<10}] verdict={r.verdict:<16} ssim={bd.get('ssim')} "
                  f"FP[{','.join(tags) if tags else '-'}]")
    finally:
        try:
            mini.shutdown()
        except Exception:
            pass
        for n in os.listdir(tmp_dir):
            try:
                os.remove(os.path.join(tmp_dir, n))
            except OSError:
                pass

    diagnosed = [r for r in results if r.get("verdict") not in ("CAPTURE_FAIL", None)]
    n = len(diagnosed)
    def _rate(key):
        return round(sum(1 for r in diagnosed if r.get(key)) / n, 3) if n else None
    summary = {
        "project": args.project,
        "pages_total": len(pages),
        "pages_diagnosed": n,
        "attach_success_rate": round(n / len(pages), 3) if pages else 0,
        # 分通道健康页假阳率：verdict 是主输出，baseline/webug 是辅助证据
        "verdict_fp_rate": _rate("verdict_fp"),
        "baseline_fp_rate": _rate("baseline_fp"),
        "webug_fp_rate": _rate("webug_fp"),
        "any_channel_fp_rate": _rate("false_positive"),
        "qwen_oracle": args.qwen,
    }
    print(f"\n[done] {summary}")

    json_out = os.path.join(AUTO_TEST_DIR, "reports", "v2_driver", f"{args.tag}_foreign_{ts}.json")
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump({"ts": ts, "summary": summary, "results": results}, f, indent=2, ensure_ascii=False)
    print(f"[done] JSON: {json_out}")

    md = [
        f"# 陌生小程序零侵入 driver 报告 @ {ts}",
        "",
        f"- project: `{args.project}`",
        f"- 页面数: {len(pages)} | 成功诊断: {n} | attach 成功率: {summary['attach_success_rate']:.0%}",
        f"- **健康页假阳率** — verdict(主): {summary['verdict_fp_rate']} | "
        f"baseline: {summary['baseline_fp_rate']} | webug: {summary['webug_fp_rate']} | 任一通道: {summary['any_channel_fp_rate']}",
        f"- Qwen 视觉 oracle: {args.qwen}",
        "",
        "> 说明：独立第三方小程序不调用本项目故障后端，无法零侵入注入故障；本报告验证的是"
        "**零集成 attach + 真实页面多通道诊断 + 健康页假阳率**（分通道），不是故障检出率。",
        "",
        "| page | verdict | baseline_ssim | verdict_fp | baseline_fp | webug_fp |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        if r.get("verdict") == "CAPTURE_FAIL":
            md.append(f"| {r['page']} | CAPTURE_FAIL | — | — | — | — |")
            continue
        md.append(f"| {r['page']} | {r['verdict']} | {r.get('baseline_ssim')} | "
                  f"{'是' if r.get('verdict_fp') else '否'} | {'是' if r.get('baseline_fp') else '否'} | "
                  f"{'是' if r.get('webug_fp') else '否'} |")
    md_out = os.path.join(AUTO_TEST_DIR, "reports", "v2_driver", f"{args.tag}_foreign_{ts}.md")
    with open(md_out, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"[done] MD  : {md_out}")
    return summary


if __name__ == "__main__":
    main()
