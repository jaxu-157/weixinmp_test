"""真实原生小程序 · 源码变异故障注入 × devtools 增强诊断 完整基准（youzouzou）。

跑在**真实微信开发者工具**里（connect 模式连用户手开会话），接入 DevtoolsProbe 读真实信号
（page.data / wx.getPerformance / 元素几何）—— 这正是 H5 路径缺的三类信号。

每个 case（可逆）：
  二进制备份源文件 → 注入1处 → 等 devtools 重编译 → relaunch 目标页
  → 采集(截图 + devtools信号) → 诊断(截图视觉 + devtools信号) → 打分
  → try/finally 二进制写回原文 + 字节级校验（youzouzou 在 .gitignore，绝不能靠 git）

对比基线：crash-only / 整图SSIM / 分块SSIM / 纯截图 / **纯devtools** / ours(全通道)
前置：用户手动打开开发者工具加载 youzouzou + 开自动化端口（--port）。

用法：
  python fault_bench/run_native_bench.py --port 33676 --project D:\\weixinmp_test\\third-youzouzou-wxapp
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for p in (REPO, HERE, os.path.join(REPO, "auto_test", "v2_modules"), os.path.join(REPO, "diagnosis")):
    if p not in sys.path:
        sys.path.insert(0, p)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from native_mutations import MUTATIONS, coarse_dim            # noqa: E402
from vt_diagnose import VTDiagnoser, tiled_min_ssim            # noqa: E402
from devtools_probe import DevtoolsProbe, signals_to_business  # noqa: E402

OUT = os.path.join(HERE, "native_out")
SHOTS = os.path.join(OUT, "screens")
DIMS = ["visual", "functional", "performance"]

SSIM_WHOLE = 0.92
SSIM_TILE = 0.85
# 性能：buggy 比 baseline 的渲染/脚本耗时多这么多 ms 视为性能故障。
# 真机健康基线 first_render≈100ms / max_script≈1-2ms；注入 1400ms 死循环远超之，阈值取 600 稳。
PERF_DELTA_MS = 600.0


def log(*a):
    print(*a, flush=True)


# ============================================================ 可逆注入（二进制，字节级）
class Mutator:
    def __init__(self, root):
        self.root = root
        self._backup = None  # (path, original_bytes)

    def apply(self, m):
        fp = os.path.join(self.root, m["file"])
        with open(fp, "rb") as f:
            orig = f.read()
        text = orig.decode("utf-8")
        if text.count(m["old"]) != 1:
            raise RuntimeError(f"marker not unique in {m['file']}: count={text.count(m['old'])}")
        self._backup = (fp, orig)
        with open(fp, "wb") as f:
            f.write(text.replace(m["old"], m["new"], 1).encode("utf-8"))

    def restore(self):
        if not self._backup:
            return
        fp, orig = self._backup
        with open(fp, "wb") as f:
            f.write(orig)
        self._backup = None

    def verify_restored(self) -> bool:
        if not self._backup:
            return True
        fp, orig = self._backup
        try:
            return open(fp, "rb").read() == orig
        except OSError:
            return False


# ============================================================ 采集
def _relaunch(app, path):
    try:
        app.relaunch(path)
    except Exception as e:
        log("    relaunch warn:", e)


def _shot(app, path):
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
    try:
        app.screen_shot(path)
    except Exception as e:
        log("    screenshot err:", e)
    return path if (os.path.exists(path) and os.path.getsize(path) > 0) else None


def capture(mini, probe, page_path, shot_path, settle=2.5):
    """relaunch 目标页 → 测导航墙钟(抓主线程阻塞) → 截图 + devtools 信号。

    导航墙钟 = relaunch + 一次同步 evaluate 往返的墙钟时间。
    若 onShow/onLoad 里有阻塞(如死循环)，appservice JS 线程被占住，
    这次 evaluate 会被排在阻塞之后才执行 → 墙钟包含阻塞时长。
    这是抓 blocking_loop 的关键（wx.getPerformance 的 firstRender 是启动一次性记录，relaunch 不刷新，抓不到）。
    """
    probe.start_perf()
    import time as _t
    t0 = _t.perf_counter()
    _relaunch(mini.app, page_path)
    try:
        mini.app.evaluate("function(){return 1}", sync=True)
    except Exception:
        pass
    nav_wall_ms = (_t.perf_counter() - t0) * 1000.0
    time.sleep(settle)
    shot = _shot(mini.app, shot_path)
    signals = probe.collect()
    signals["nav_wall_ms"] = nav_wall_ms   # 放进 signals 供 diagnose 读
    return {"shot": shot, "signals": signals, "nav_wall_ms": nav_wall_ms}


# ============================================================ 性能代理 / 诊断
def _perf_metric(perf_sig):
    """运行时性能代理：firstRender 与 最长 script 的最大值（app_launch 一次性启动，排除）。"""
    vals = [perf_sig.get(k) for k in ("first_render_ms", "max_script_ms")]
    vals = [v for v in vals if isinstance(v, (int, float))]
    return max(vals) if vals else None


def diagnose_case(diag, page, shot, baseline_shot, signals, baseline_perf):
    ch = {"crash": False, "visual_verdict": False, "ssim_whole": False, "ssim_tile": False,
          "dt_data": False, "dt_geom": False, "dt_perf": False}
    verdict = "Pass"
    whole_ssim = tile_ssim = None

    # --- 截图视觉通道 ---
    if shot and baseline_shot:
        try:
            diag.set_baseline(page, baseline_shot)
            r = diag.diagnose(page, shot)
            verdict = r["verdict"]
            ch["visual_verdict"] = verdict not in ("Pass", "Unknown")
            whole_ssim = r["channels"]["baseline_ssim"]
            ch["ssim_whole"] = bool(whole_ssim is not None and whole_ssim < SSIM_WHOLE)
            tile_ssim = r["channels"].get("tiled_min_ssim")
            ch["ssim_tile"] = bool(tile_ssim is not None and tile_ssim < SSIM_TILE)
            ch["crash"] = bool(r["visual"].get("black_white"))
        except Exception as e:
            log("    visual diagnose err:", e)

    # --- devtools 信号通道 ---
    data_sig = signals.get("data_signal", {})
    geo_sig = signals.get("geometry_signal", {})
    perf_sig = signals.get("perf_signal", {})
    ch["dt_data"] = bool(data_sig.get("has_suspicious"))
    ch["dt_geom"] = bool(geo_sig.get("has_overflow"))  # 只信 overflow（可靠），overlap 不采信
    # 性能（诚实版）：零侵入只用 wx.getPerformance 相对基线超 PERF_DELTA_MS 判。
    # 已知局限：wx.getPerformance 的 firstRender 是启动一次性记录、relaunch 不刷新，
    # onShow 同步阻塞抓不到（见报告"性能维盲区"）。此通道保守，宁可漏不可误报，
    # 以免像导航墙钟那版把视觉/数据故障误判成 performance（已回退）。
    base_gp = baseline_perf.get("gp") if isinstance(baseline_perf, dict) else baseline_perf
    cur_metric = _perf_metric(perf_sig)
    perf_hit = False
    if isinstance(cur_metric, (int, float)) and isinstance(base_gp, (int, float)):
        perf_hit = (cur_metric - base_gp) > PERF_DELTA_MS
    ch["dt_perf"] = perf_hit
    cur_wall = signals.get("nav_wall_ms")  # 仅记录用，不参与判定（实测采不到，全 None）
    if False:  # 占位，保持下方 cur_script 赋值结构
        pass

    detected = any(ch[k] for k in ("visual_verdict", "ssim_whole", "ssim_tile", "dt_data", "dt_geom", "dt_perf"))
    if ch["dt_perf"]:
        pred = "performance"
    elif ch["dt_data"]:
        pred = "functional"
    elif ch["visual_verdict"] or ch["ssim_whole"] or ch["ssim_tile"] or ch["dt_geom"]:
        pred = "visual"
    else:
        pred = "none"
    return {"channels": ch, "detected": detected, "pred_dim": pred, "verdict": verdict,
            "whole_ssim": whole_ssim, "tile_ssim": tile_ssim, "perf_metric": cur_metric}


# ============================================================ 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--cli", default=r"D:\wx_mp_tool2\微信web开发者工具\cli.bat")
    ap.add_argument("--recompile-wait", type=float, default=4.0)
    args = ap.parse_args()

    os.makedirs(SHOTS, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    root = args.project
    mut = Mutator(root)

    pages = []
    for m in MUTATIONS:
        if (m["page"], m["page_path"]) not in pages:
            pages.append((m["page"], m["page_path"]))

    config = {
        "project_path": root, "dev_tool_path": args.cli, "test_port": args.port,
        "appid": "", "debug_mode": "error", "enable_app_log": True,
        "auto_relaunch": False, "auto_quit_ide": False, "request_timeout": 60,
        "device_desktop": {"width": 375, "height": 667},
    }

    import minium
    log("[native] connecting minium (connect, port %d)..." % args.port)
    mini = minium.Minium(config)
    log("[native] connected.\n")
    probe = DevtoolsProbe(mini)
    diag = VTDiagnoser(use_learned=True, use_cascade=False)

    cases = []
    baseline_shots, baseline_perf = {}, {}

    try:
        # ---------- 阶段0：warmup（消除冷启动对 nav_wall 基线的干扰）----------
        log("[phase0] warmup（冷启动预热，丢弃式）")
        mut.restore()
        for page, path in pages:
            try:
                capture(mini, probe, path, os.path.join(SHOTS, f"_warmup_{page}.png"), settle=1.5)
            except Exception:
                pass

        # ---------- 阶段1：健康基线 ----------
        log("[phase1] 健康基线（未注入）")
        for page, path in pages:
            cap = capture(mini, probe, path, os.path.join(SHOTS, f"baseline_{page}.png"))
            baseline_shots[page] = cap["shot"]
            gp = _perf_metric(cap["signals"].get("perf_signal", {}))
            baseline_perf[page] = {"gp": gp if isinstance(gp, (int, float)) else 0.0,
                                   "wall": cap.get("nav_wall_ms")}
            geo = cap["signals"].get("geometry_signal", {})
            log(f"  baseline {page:<10} shot={'OK' if cap['shot'] else 'FAIL'} "
                f"base_gp={baseline_perf[page]['gp']}ms base_wall={round(baseline_perf[page]['wall'] or 0)}ms "
                f"overflow={geo.get('has_overflow')}")

        # ---------- 阶段2：健康对照（测假阳）----------
        log("\n[phase2] 健康对照（重采，测假阳）")
        for page, path in pages:
            cap = capture(mini, probe, path, os.path.join(SHOTS, f"healthy_{page}.png"))
            res = diagnose_case(diag, page, cap["shot"], baseline_shots.get(page),
                                cap["signals"], baseline_perf.get(page))
            cases.append({"id": f"healthy_{page}", "kind": "healthy", "page": page,
                          "gt_dim": "none", **res})
            log(f"  healthy  {page:<10} detected={res['detected']} pred={res['pred_dim']} "
                f"ch={_chstr(res['channels'])}")

        # ---------- 阶段3：逐变异注入 ----------
        log("\n[phase3] 源码变异注入（可逆）")
        for m in MUTATIONS:
            page, path = m["page"], m["page_path"]
            log(f"\n[mut] {m['id']} (gt={m['dim']}, page={page})")
            try:
                mut.apply(m)
                log(f"    injected → {m['file']}; recompile wait {args.recompile_wait}s")
                time.sleep(args.recompile_wait)
                cap = capture(mini, probe, path, os.path.join(SHOTS, f"{m['id']}.png"))
                res = diagnose_case(diag, page, cap["shot"], baseline_shots.get(page),
                                    cap["signals"], baseline_perf.get(page))
                gt = coarse_dim(m["dim"])
                sg = cap["signals"]
                rec = {"id": m["id"], "kind": "fault", "page": page, "gt_dim": gt,
                       "gt_fine": m["dim"], "subtype": m["subtype"], "note": m["note"],
                       "rca_correct": res["pred_dim"] == gt, **res,
                       "dt_summary": {
                           "data_tokens": sg.get("data_signal", {}).get("suspicious_tokens"),
                           "geom_overflow": sg.get("geometry_signal", {}).get("has_overflow"),
                           "geom_scrollW": sg.get("geometry_signal", {}).get("scroll_width"),
                           "geom_clientW": sg.get("geometry_signal", {}).get("client_width"),
                           "perf_metric": res["perf_metric"],
                           "nav_wall_ms": round(res.get("nav_wall_ms") or 0),
                           "base_wall_ms": round((baseline_perf.get(page) or {}).get("wall") or 0),
                       }}
                cases.append(rec)
                log(f"    detected={res['detected']} pred={res['pred_dim']} gt={gt} "
                    f"{'OK' if rec['rca_correct'] else 'XX'} verdict={res['verdict']} "
                    f"tile={res['tile_ssim']} wall={round(res.get('nav_wall_ms') or 0)}ms(base={round((baseline_perf.get(page) or {}).get('wall') or 0)}ms)")
                log(f"    dt: {rec['dt_summary']}")
            except Exception as e:
                log(f"    ERROR: {e}")
                traceback.print_exc()
                cases.append({"id": m["id"], "kind": "fault", "page": page,
                              "gt_dim": coarse_dim(m["dim"]), "error": str(e)})
            finally:
                mut.restore()
                ok = mut.verify_restored()
                log(f"    restored {m['file']} (字节级可逆={ok})")
    finally:
        mut.restore()  # 双保险
        log("\n[native] done. (connect 模式不调 shutdown；进程退出自动断连，工具/项目保持打开)")

    report = score(cases)
    os.makedirs(OUT, exist_ok=True)
    jp = os.path.join(OUT, f"native_report_{ts}.json")
    with open(jp, "w", encoding="utf-8") as f:
        json.dump({"ts": ts, "project": root, "cases": cases, "report": report},
                  f, ensure_ascii=False, indent=2, default=str)
    mp = os.path.join(OUT, f"native_report_{ts}.md")
    with open(mp, "w", encoding="utf-8") as f:
        f.write(render_md(cases, report, ts, root))
    log(f"\n[done] JSON {jp}")
    log(f"[done] MD   {mp}")
    log("\n=== SUMMARY ===")
    log(json.dumps(report["headline"], ensure_ascii=False, indent=2))


def _chstr(ch):
    return "+".join(k for k, v in ch.items() if v) or "-"


def _prf(tp, fp, fn):
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return round(p, 3), round(r, 3), round(f, 3)


def score(cases):
    faults = [c for c in cases if c["kind"] == "fault" and "error" not in c]
    healthy = [c for c in cases if c["kind"] == "healthy"]
    nf, nh = len(faults), len(healthy)

    methods = {
        "crash_only": lambda c: c["channels"]["crash"],
        "ssim_whole_only": lambda c: c["channels"]["ssim_whole"],
        "ssim_tiled_only": lambda c: c["channels"]["ssim_tile"],
        "screenshot_only": lambda c: (c["channels"]["visual_verdict"] or c["channels"]["ssim_whole"]
                                      or c["channels"]["ssim_tile"]),
        "devtools_only": lambda c: (c["channels"]["dt_data"] or c["channels"]["dt_geom"]
                                    or c["channels"]["dt_perf"]),
        "ours_all": lambda c: c["detected"],
    }
    detection = {}
    for name, fn in methods.items():
        rec = sum(1 for c in faults if fn(c)) / nf if nf else 0
        fp = sum(1 for c in healthy if fn(c)) / nh if nh else 0
        detection[name] = {"recall": round(rec, 3), "fp": round(fp, 3),
                           "n_detected": sum(1 for c in faults if fn(c))}

    import collections
    conf = {g: collections.Counter() for g in DIMS}
    for c in faults:
        conf[c["gt_dim"]][c["pred_dim"]] += 1
    per_class, macro = {}, []
    for d in DIMS:
        tp = conf[d][d]
        fp = sum(conf[g][d] for g in DIMS if g != d)
        fn = sum(v for p, v in conf[d].items() if p != d)
        p, r, f = _prf(tp, fp, fn)
        per_class[d] = {"precision": p, "recall": r, "f1": f, "tp": tp, "fp": fp, "fn": fn}
        macro.append(f)
    rca_top1 = round(sum(1 for c in faults if c["pred_dim"] == c["gt_dim"]) / nf, 3) if nf else 0
    n_det = sum(1 for c in faults if c["detected"])
    n_det_correct = sum(1 for c in faults if c["detected"] and c["pred_dim"] == c["gt_dim"])

    headline = {
        "n_faults": nf, "n_healthy": nh,
        "ours_recall": detection["ours_all"]["recall"], "ours_fp": detection["ours_all"]["fp"],
        "crash_only_recall": detection["crash_only"]["recall"],
        "screenshot_only_recall": detection["screenshot_only"]["recall"],
        "devtools_only_recall": detection["devtools_only"]["recall"],
        "rca_top1": rca_top1, "rca_macro_f1": round(sum(macro) / len(macro), 3) if macro else 0,
        "rca_correct_given_detected": f"{n_det_correct}/{n_det}",
    }
    return {"headline": headline, "detection": detection, "rca_per_class": per_class}


def render_md(cases, report, ts, root):
    h = report["headline"]
    L = [f"# 真实原生小程序 源码变异故障注入 × devtools 增强诊断 — youzouzou\n",
         f"_run {ts} · `{os.path.basename(root)}`（原生 WXML，48 页）· 微信开发者工具 connect 模式 · 可逆注入_\n",
         "## Headline\n",
         f"- 故障 **{h['n_faults']}** / 健康对照 **{h['n_healthy']}**",
         f"- **ours(全通道) recall {h['ours_recall']:.0%} / 健康假阳 {h['ours_fp']:.0%}**",
         f"- crash-only **{h['crash_only_recall']:.0%}** · 纯截图 {h['screenshot_only_recall']:.0%} · "
         f"**纯 devtools {h['devtools_only_recall']:.0%}**（互补性见逐用例）",
         f"- RCA top-1 **{h['rca_top1']:.0%}**（检出即对 {h['rca_correct_given_detected']}）· macro-F1 {h['rca_macro_f1']:.2f}\n",
         "## 检测：各通道对比\n",
         "| 方法 | recall@故障 | 假阳@健康 |", "|---|---|---|"]
    for name, d in report["detection"].items():
        L.append(f"| {name} | {d['recall']:.0%} | {d['fp']:.0%} |")
    L += ["", "## RCA 每维度\n", "| 维度 | P | R | F1 | tp | fp | fn |", "|---|---|---|---|---|---|---|"]
    for dim, m in report["rca_per_class"].items():
        L.append(f"| {dim} | {m['precision']:.2f} | {m['recall']:.2f} | {m['f1']:.2f} | {m['tp']} | {m['fp']} | {m['fn']} |")
    L += ["", "## 逐用例（截图通道 vs devtools 通道 互补）\n",
          "| case | gt | pred | 检出 | 截图verdict | tileSSIM | devtools信号 | note |",
          "|---|---|---|---|---|---|---|---|"]
    for c in cases:
        if "error" in c:
            L.append(f"| {c['id']} | {c.get('gt_dim','-')} | — | ERROR | {c['error'][:40]} |  |  |  |")
            continue
        dt = c.get("dt_summary", {})
        ds = []
        if dt.get("data_tokens"):
            ds.append(f"data={dt['data_tokens']}")
        if dt.get("geom_overflow"):
            ds.append(f"overflow(sw{dt.get('geom_scrollW')}/cw{dt.get('geom_clientW')})")
        if dt.get("perf_metric"):
            ds.append(f"perf={dt['perf_metric']}ms")
        L.append(f"| {c['id']} | {c['gt_dim']} | {c['pred_dim']} | "
                 f"{'✅' if c['detected'] else '❌'} | {c.get('verdict','-')} | "
                 f"{c.get('tile_ssim','-')} | {'; '.join(ds) if ds else '-'} | {c.get('note','')} |")
    L += ["", "> 可逆性：每个变异二进制备份 + try/finally 写回原始字节 + 字节级校验（youzouzou 在 .gitignore，不靠 git）。",
          "> devtools 信号 = page.data token 扫描 + 元素几何(scrollWidth 溢出) + wx.getPerformance 渲染/脚本耗时。",
          "> connect 模式不调 shutdown，工具/项目保持打开。"]
    return "\n".join(L)


if __name__ == "__main__":
    main()
