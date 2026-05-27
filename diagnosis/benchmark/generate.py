"""生成可复现的 Vision-Triage Fault Benchmark。

输出 JSON：每条样本含 (page, profile, intensity, features, expected_verdict)。
intensity ∈ [0, 1]：0 是该 profile 的最弱表现，1 是最强表现。
故意覆盖边界区（intensity ≈ 0.4-0.6），让 oracle 的鲁棒性能被验证。

注意：本 benchmark 是"特征级"的，不依赖实跑小程序——这样可复现性强、
评测延迟低。它评测的是 oracle 把 (visual + perf + functional) 特征映射到
verdict 的能力，与 Phase 4b 的"端到端在真实小程序上跑"是互补的两层评测。
"""
from __future__ import annotations

import os
import sys
import json
import argparse
import random
from typing import List, Tuple, Dict

# 让 `python diagnosis/benchmark/generate.py` 也能直接跑：需要把 diagnosis/ 加入路径
_THIS = os.path.dirname(os.path.abspath(__file__))
_DIAGNOSIS_DIR = os.path.dirname(_THIS)
if _DIAGNOSIS_DIR not in sys.path:
    sys.path.insert(0, _DIAGNOSIS_DIR)

from diagnose.feature_extractor import FEATURE_NAMES, VERDICTS, extract_features  # noqa: E402


# (page, profile, expected_verdict, intensity_axis)
# intensity_axis 描述这个 profile 的"强弱"维度由哪个特征体现
SCENARIOS = [
    ("feed", "normal", "Pass", "perfect_normal"),
    ("feed", "slow_api", "PerformanceRisk", "interaction_ms"),
    ("feed", "blur_image", "RenderBug", "blur_intensity"),
    ("feed", "memory_pressure", "PerformanceRisk", "memory_warnings"),
    ("feed", "mixed_fault", "Mixed", "compound"),
    ("counter", "normal", "Pass", "perfect_normal"),
    ("counter", "slow_api", "PerformanceRisk", "interaction_ms"),
    ("counter", "stale_ui", "FunctionalFail", "visible_diff"),
    ("counter", "wrong_mapping", "FunctionalFail", "visible_diff"),
    ("counter", "mixed_fault", "Mixed", "compound"),
    ("layout", "normal", "Pass", "perfect_normal"),
    ("layout", "slow_api", "PerformanceRisk", "interaction_ms"),
    ("layout", "layout_overlap", "FunctionalFail", "overlap"),
    ("layout", "memory_pressure", "PerformanceRisk", "memory_warnings"),
]


def _make_visual_normal(rng: random.Random) -> Dict:
    return {
        "blur_score_full": rng.uniform(450, 900),
        "blur_score": rng.uniform(250, 500),
        "edge_density": rng.uniform(0.08, 0.22),
        "mean_brightness": rng.uniform(140, 200),
        "black_white": False,
        "is_blur": False,
        "ocr_text": "样本文本" * rng.randint(2, 8),
    }


def _make_visual_blur(rng: random.Random, intensity: float) -> Dict:
    # intensity 越高，模糊越严重
    blur_full = 50.0 + (1.0 - intensity) * 80.0 + rng.gauss(0, 10)
    blur_card = 30.0 + (1.0 - intensity) * 60.0 + rng.gauss(0, 8)
    edge = 0.02 + (1.0 - intensity) * 0.04 + rng.gauss(0, 0.005)
    return {
        "blur_score_full": max(5.0, blur_full),
        "blur_score": max(5.0, blur_card),
        "edge_density": max(0.0, edge),
        "mean_brightness": rng.uniform(120, 180),
        "black_white": False,
        "is_blur": blur_full < 100,
        "ocr_text": "" if intensity > 0.7 else "模糊文本",
    }


def _make_perf_normal(rng: random.Random) -> Dict:
    return {
        "pass": True,
        "interaction_ms": rng.uniform(50, 200),
        "memory_warnings": 0,
    }


def _make_perf_slow(rng: random.Random, intensity: float) -> Dict:
    # intensity 越高，延迟越严重；带边界区
    ms = 600.0 + intensity * 900.0 + rng.gauss(0, 80)
    return {
        "pass": ms <= 800.0,
        "interaction_ms": max(100.0, ms),
        "memory_warnings": 0,
    }


def _make_perf_memory(rng: random.Random, intensity: float) -> Dict:
    warnings = 1 if intensity > 0.3 else 0
    if intensity > 0.7:
        warnings = rng.randint(1, 3)
    return {
        "pass": warnings == 0,
        "interaction_ms": rng.uniform(100, 400),
        "memory_warnings": warnings,
    }


def _build_sample(
    page: str,
    profile: str,
    verdict: str,
    axis: str,
    intensity: float,
    rng: random.Random,
) -> Tuple[List[float], Dict]:
    """构造一个样本：返回 (features, metadata)。"""
    visual = _make_visual_normal(rng)
    performance = _make_perf_normal(rng)
    functional = {"pass": True}
    page_state: Dict = {}

    if profile == "slow_api":
        performance = _make_perf_slow(rng, intensity)
    elif profile == "blur_image":
        visual = _make_visual_blur(rng, intensity)
    elif profile == "memory_pressure":
        performance = _make_perf_memory(rng, intensity)
    elif profile == "stale_ui":
        functional = {"pass": False}
        page_state = {"visibleValue": 0, "expectedValue": 1}
    elif profile == "wrong_mapping":
        functional = {"pass": False}
        page_state = {"visibleValue": "undefined", "expectedValue": 1}
    elif profile == "layout_overlap":
        functional = {"pass": False}
        page_state = {"uiFlags": {"hasOverlap": True}}
    elif profile == "mixed_fault":
        performance = _make_perf_slow(rng, max(0.6, intensity))
        if page == "feed":
            visual = _make_visual_blur(rng, max(0.6, intensity))
        elif page == "counter":
            functional = {"pass": False}
            page_state = {"visibleValue": 0, "expectedValue": 1}

    feats = extract_features(visual, functional, performance, page, page_state)
    meta = {
        "blur_score_full": visual["blur_score_full"],
        "blur_score": visual["blur_score"],
        "edge_density": visual["edge_density"],
        "interaction_ms": performance["interaction_ms"],
        "memory_warnings": performance["memory_warnings"],
        "functional_pass": functional["pass"],
        "is_borderline": 0.35 <= intensity <= 0.65,
    }
    return feats, meta


def generate(
    samples_per_scenario: int = 20,
    seed: int = 42,
    out_path: str | None = None,
) -> Dict:
    rng = random.Random(seed)
    samples = []
    for page, profile, verdict, axis in SCENARIOS:
        for i in range(samples_per_scenario):
            intensity = i / max(samples_per_scenario - 1, 1)
            feats, meta = _build_sample(page, profile, verdict, axis, intensity, rng)
            samples.append({
                "id": f"{page}_{profile}_{i:03d}",
                "page": page,
                "profile": profile,
                "intensity": round(intensity, 3),
                "intensity_axis": axis,
                "features": feats,
                "expected_verdict": verdict,
                "metadata": meta,
            })

    bench = {
        "version": "v1",
        "schema": {
            "feature_names": FEATURE_NAMES,
            "verdicts": list(VERDICTS),
        },
        "config": {
            "scenarios": [
                {"page": p, "profile": pr, "verdict": v, "axis": a}
                for p, pr, v, a in SCENARIOS
            ],
            "samples_per_scenario": samples_per_scenario,
            "seed": seed,
        },
        "n_samples": len(samples),
        "samples": samples,
    }

    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(bench, f, indent=2, ensure_ascii=False)
        print(f"benchmark saved: {out_path}  ({len(samples)} samples)")

    return bench


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-scenario", type=int, default=25)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=str,
                        default=os.path.join(os.path.dirname(__file__), "vt_bench_v1.json"))
    args = parser.parse_args()
    bench = generate(samples_per_scenario=args.per_scenario, seed=args.seed, out_path=args.out)
    # 类别分布
    from collections import Counter
    c = Counter(s["expected_verdict"] for s in bench["samples"])
    print(f"verdict distribution: {dict(c)}")
    bord = sum(1 for s in bench["samples"] if s["metadata"]["is_borderline"])
    print(f"borderline samples: {bord} ({bord/len(bench['samples']):.1%})")
