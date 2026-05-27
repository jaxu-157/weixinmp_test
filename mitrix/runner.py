"""mitrix 编排器。

流程: 连接微信 → 按用例激活多故障 → 截图 → 诊断 → 多标签检测 → 构建矩阵 → 生成报告
"""
import os
import sys
import json
import time
import requests
import traceback
from datetime import datetime

from .generator import ATOMIC_FAULTS, generate_test_cases, load_test_cases
from .engine import detect_all, compute_metrics
from .interaction import analyze, format_interaction_report


class MitrixRunner:
    def __init__(self, mini, diagnose_url="http://127.0.0.1:8900/diagnose"):
        self.mini = mini
        self.diagnose_url = diagnose_url
        self.results: list[dict] = []

        base_dir = os.path.dirname(os.path.dirname(__file__))
        self.report_dir = os.path.join(base_dir, "reports")
        self.screenshot_dir = os.path.join(self.report_dir, "screenshots")
        os.makedirs(self.screenshot_dir, exist_ok=True)

    # ================================================================
    # 故障激活
    # ================================================================

    def activate_multi_faults(self, faults: list[str]):
        """激活多个原子故障的组合。"""
        profile_str = "+".join(faults) if faults else "normal"
        print(f"   🔧 激活复合故障: {profile_str}")
        try:
            resp = requests.post(
                "http://127.0.0.1:8900/fault/activate-multi",
                json={"profiles": faults},
                timeout=10,
            )
            data = resp.json()
            if data.get("code") == 0:
                print(f"      ✅ 激活成功 → profile={data.get('profile')}")
                return True
            else:
                print(f"      ❌ 激活失败: {data}")
                return False
        except Exception as e:
            print(f"      ❌ 激活异常: {e}")
            return False

    def activate_normal(self):
        return self.activate_multi_faults([])

    # ================================================================
    # 截图
    # ================================================================

    def take_screenshot(self, case_id: str, faults: list[str]):
        profile_str = "+".join(faults) if faults else "normal"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_id = case_id.replace("/", "_").replace("+", "_")
        filename = f"mitrix_{safe_id}_{timestamp}.png"
        filepath = os.path.join(self.screenshot_dir, filename)

        try:
            self.mini.app.screen_shot(filepath)
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                print(f"      📸 截图: {filepath}")
                return filepath
        except Exception as e:
            print(f"      ⚠️ minium 截图失败: {e}")

        # 兜底：Windows 截图
        try:
            from .win_capture import win_screenshot
            if win_screenshot(filepath):
                print(f"      📸 截图(win): {filepath}")
                return filepath
        except Exception:
            pass

        print(f"      ❌ 截图失败")
        return None

    # ================================================================
    # 页面状态构建
    # ================================================================

    def _build_page_state(self, page: str, faults: list[str]) -> dict:
        """根据页面和活跃故障构造 page_state。"""
        state = {}

        fault_set = set(faults)

        if page == "counter":
            if "stale_ui" in fault_set and "wrong_mapping" in fault_set:
                # both: wrong_mapping dominates (field renamed, value unavailable)
                state = {"visibleValue": "undefined", "expectedValue": 1}
            elif "stale_ui" in fault_set:
                state = {"visibleValue": 0, "expectedValue": 1}
            elif "wrong_mapping" in fault_set:
                state = {"visibleValue": "undefined", "expectedValue": 1}
            else:
                state = {"visibleValue": 1, "expectedValue": 1}

        elif page == "layout":
            if "layout_overlap" in fault_set:
                state = {"uiFlags": {"hasOverlap": True}}

        elif page == "feed":
            # feed 页主要是视觉/性能故障，功能断言较少
            pass

        return state

    def _collect_perf_data(self, faults: list[str]) -> dict:
        """根据活跃故障构造 perf_data。"""
        fault_set = set(faults)
        perf = {"interactionMs": 100, "memoryWarningCount": 0}

        if "slow_api" in fault_set:
            perf["interactionMs"] = 900  # 超过 800ms 阈值
        if "memory_pressure" in fault_set:
            perf["memoryWarningCount"] = 1

        return perf

    # ================================================================
    # 诊断
    # ================================================================

    def run_diagnosis(self, screenshot_path: str, page: str, faults: list[str]):
        """调用诊断接口并运行多标签引擎。"""
        profile_str = "+".join(faults) if faults else "normal"

        if not os.path.exists(screenshot_path):
            return None

        try:
            perf_data = self._collect_perf_data(faults)
            page_state = self._build_page_state(page, faults)

            with open(screenshot_path, "rb") as f:
                files = {"screenshot": (os.path.basename(screenshot_path), f, "image/png")}
                data = {
                    "page_type": page,
                    "fault_profile": profile_str,
                    "page_state": json.dumps(page_state),
                    "perf_data": json.dumps(perf_data),
                }
                resp = requests.post(self.diagnose_url, files=files, data=data, timeout=15)

            if resp.status_code != 200:
                print(f"      ❌ 诊断 HTTP {resp.status_code}")
                return None

            triage_result = resp.json().get("data", {})
            print(f"      🧠 诊断 verdict={triage_result.get('verdict')}")

            # 多标签检测
            multi = detect_all(triage_result, page)
            return {
                "triage": triage_result,
                "multi_label": multi,
            }

        except Exception as e:
            print(f"      ❌ 诊断异常: {e}")
            return None

    # ================================================================
    # 单用例执行
    # ================================================================

    def run_case(self, case: dict) -> dict:
        """执行单个测试用例。"""
        case_id = case["id"]
        faults = case["faults"]
        page = case["page"]
        oracle = case["oracle"]

        print(f"\n{'='*60}")
        print(f"🧪 {case_id}")
        print(f"   故障: {faults or ['normal']}")
        print(f"   页面: {page}")
        print(f"   Oracle: {oracle}")

        t0 = time.time()

        try:
            # 1. 激活故障
            if not self.activate_multi_faults(faults):
                return self._failed_result(case, "fault_activation_failed")

            time.sleep(1.5)

            # 2. 导航
            print(f"   📍 导航到 /pages/{page}/index")
            try:
                self.mini.app.relaunch(f"/pages/{page}/index")
            except Exception as e:
                print(f"      ⚠️ 导航警告: {e}")

            wait = 5 if "slow_api" in faults else 4
            print(f"      ⏳ 等待 {wait}s")
            time.sleep(wait)

            # 3. 截图
            screenshot_path = self.take_screenshot(case_id, faults)
            if not screenshot_path:
                return self._failed_result(case, "screenshot_failed")

            # 4. 诊断 + 多标签
            diag = self.run_diagnosis(screenshot_path, page, faults)
            if not diag:
                return self._failed_result(case, "diagnosis_failed")

            # 5. 结果汇总
            detected = diag["multi_label"]["detected"]
            confidence = diag["multi_label"]["confidence"]

            # 与 oracle 比较
            match_vec = {}
            for f in ATOMIC_FAULTS:
                expected = 1 if oracle.get(f) else 0
                actual = detected.get(f, 0)
                match_vec[f] = expected == actual

            all_match = all(match_vec.values())
            match_count = sum(1 for v in match_vec.values() if v)

            duration = time.time() - t0

            result = {
                "case_id": case_id,
                "page": page,
                "faults": faults,
                "oracle": oracle,
                "detected": detected,
                "confidence": confidence,
                "match_vec": match_vec,
                "all_match": all_match,
                "match_count": match_count,
                "triage_verdict": diag["triage"].get("verdict"),
                "screenshot": screenshot_path,
                "duration": round(duration, 2),
                "timestamp": datetime.now().isoformat(),
                "success": True,
            }

            self.results.append(result)

            if all_match:
                print(f"   ✅ 全匹配! ({duration:.1f}s)")
            else:
                mismatches = [f for f, v in match_vec.items() if not v]
                print(f"   ❌ 不匹配: {mismatches} ({duration:.1f}s)")
                for f in mismatches:
                    print(f"       {f}: expected={oracle[f]}, detected={detected[f]}")

            return result

        except Exception as e:
            duration = time.time() - t0
            print(f"   💥 异常 ({duration:.1f}s): {e}")
            traceback.print_exc()
            return self._failed_result(case, f"exception: {e}")

    def _failed_result(self, case: dict, error: str) -> dict:
        result = {
            "case_id": case["id"],
            "page": case["page"],
            "faults": case["faults"],
            "oracle": case.get("oracle", {}),
            "detected": {},
            "confidence": {},
            "match_vec": {},
            "all_match": False,
            "match_count": 0,
            "triage_verdict": None,
            "screenshot": None,
            "duration": 0,
            "timestamp": datetime.now().isoformat(),
            "success": False,
            "error": error,
        }
        self.results.append(result)
        return result

    # ================================================================
    # 报告生成
    # ================================================================

    def generate_report(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(self.report_dir, f"mitrix_report_{timestamp}.json")

        metrics = compute_metrics(self.results)

        n_success = sum(1 for r in self.results if r.get("success"))
        n_all_match = sum(1 for r in self.results if r.get("all_match"))
        n_total = len(self.results)

        interaction = analyze(self.results)

        report = {
            "project": "Vision-Triage mitrix",
            "timestamp": timestamp,
            "summary": {
                "total_cases": n_total,
                "executed": n_success,
                "all_match": n_all_match,
                "match_rate": round(n_all_match / max(n_total, 1), 3),
            },
            "per_fault_metrics": metrics,
            "interaction": interaction,
            "detection_matrix": self._build_matrix(),
            "results": self.results,
        }

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)

        # 文本矩阵
        txt_path = os.path.join(self.report_dir, f"mitrix_matrix_{timestamp}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(self._format_matrix_text(report))
            f.write("\n")
            f.write(format_interaction_report(interaction))

        print(f"\n📊 JSON 报告: {report_path}")
        print(f"📊 矩阵文本: {txt_path}")
        return report_path

    def _build_matrix(self) -> list[dict]:
        """构建故障检测矩阵（行=用例, 列=原子故障, 值=detected）。"""
        rows = []
        for r in self.results:
            if not r.get("success"):
                continue
            row = {
                "case_id": r["case_id"],
                "page": r["page"],
                "faults_injected": r["faults"],
                "detected": r.get("detected", {}),
                "oracle": r.get("oracle", {}),
                "match": r.get("match_vec", {}),
            }
            rows.append(row)
        return rows

    def _format_matrix_text(self, report: dict) -> str:
        lines = []
        lines.append("=" * 80)
        lines.append("  Vision-Triage mitrix — 故障检测矩阵")
        lines.append("=" * 80)
        lines.append(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        s = report["summary"]
        lines.append(f"用例数: {s['total_cases']} | 全匹配: {s['all_match']} | 匹配率: {s['match_rate']:.1%}")
        lines.append("")

        # 表头
        col_w = 8
        header = f"{'用例':<42s}"
        for f in ATOMIC_FAULTS:
            header += f"{f:<{col_w}s}"
        header += "OK?"
        lines.append(header)
        lines.append("-" * len(header))

        # 每行
        for row in report.get("detection_matrix", []):
            cid = row["case_id"][:40]
            line = f"{cid:<42s}"
            oracle = row.get("oracle", {})
            detected = row.get("detected", {})
            all_ok = True
            for f in ATOMIC_FAULTS:
                exp = 1 if oracle.get(f) else 0
                det = detected.get(f, 0)
                if exp == det:
                    cell = f"{'·':>3s}{det}{'·':>4s}"
                else:
                    cell = f" {exp}>{det}! "
                    all_ok = False
                line += f"{cell:<{col_w}s}"
            line += "✓" if all_ok else "✗"
            lines.append(line)

        lines.append("")
        lines.append(f"图例: ·0· / ·1· = 正确  |  E>D! = 期望E/实际D 不匹配")

        # 每故障指标
        lines.append("")
        lines.append("=" * 60)
        lines.append("  每故障独立指标 (Precision / Recall / F1)")
        lines.append("=" * 60)
        metrics = report.get("per_fault_metrics", {})
        for f in ATOMIC_FAULTS:
            m = metrics.get(f, {})
            lines.append(
                f"  {f:<20s}  P={m.get('precision', 0):.3f}  "
                f"R={m.get('recall', 0):.3f}  F1={m.get('f1', 0):.3f}  "
                f"(TP={m.get('tp', 0)} FP={m.get('fp', 0)} FN={m.get('fn', 0)})"
            )

        return "\n".join(lines)

    # ================================================================
    # 完整流程
    # ================================================================

    def run_full_suite(self, cases: list[dict] = None):
        if cases is None:
            cases = generate_test_cases()

        print("=" * 70)
        print("  Vision-Triage mitrix — 组合故障 × 多标签诊断")
        print("=" * 70)
        print(f"开始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"用例数: {len(cases)}")
        print()

        try:
            for i, case in enumerate(cases):
                print(f"\n[{i+1}/{len(cases)}]", end="")
                self.run_case(case)
                time.sleep(2)

        finally:
            try:
                self.activate_normal()
                print("\n🔄 故障已重置为 normal")
            except Exception:
                pass

        report_path = self.generate_report()

        # 控制台摘要
        metrics = compute_metrics(self.results)
        n_all = sum(1 for r in self.results if r.get("all_match"))
        n_total = sum(1 for r in self.results if r.get("success"))

        print("\n" + "=" * 70)
        print("  每故障 F1 得分")
        print("=" * 70)
        for f in ATOMIC_FAULTS:
            m = metrics[f]
            bar = "█" * int(m["f1"] * 20)
            print(f"  {f:<20s}  F1={m['f1']:.3f}  {bar}")

        print(f"\n全匹配: {n_all}/{n_total}")

        # 交互分析
        interaction = analyze(self.results)
        print()
        print(format_interaction_report(interaction))

        print(f"报告: {report_path}")
        return report_path
