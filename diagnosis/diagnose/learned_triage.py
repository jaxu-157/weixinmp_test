"""可学习分诊：用训练好的决策树替换 triage._decide_verdict。

API 与 triage.run_triage 对齐——上层调用方零改动。

使用方式：
    from diagnose.learned_triage import run_triage_learned
    result = run_triage_learned(image_bytes, page_type, ...)

或者通过环境变量切换：
    USE_LEARNED_TRIAGE=1   # app.py 会自动调 learned 版本
"""
from __future__ import annotations

import os
import json
import threading
from typing import Optional

import joblib
import numpy as np

from .feature_extractor import extract_features, FEATURE_NAMES, VERDICTS
from . import triage as rule_triage
from .cascade_oracle import CascadeOracle


_MODEL_LOCK = threading.Lock()
_BUNDLE: Optional[dict] = None


def _model_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "training", "models", "triage_tree_v1.pkl")


def _load_bundle() -> dict:
    global _BUNDLE
    if _BUNDLE is not None:
        return _BUNDLE
    with _MODEL_LOCK:
        if _BUNDLE is None:
            path = _model_path()
            if not os.path.exists(path):
                raise FileNotFoundError(
                    f"分诊模型未找到: {path}\n"
                    f"请先运行: python diagnosis/diagnose/training/train.py"
                )
            _BUNDLE = joblib.load(path)
            saved_features = _BUNDLE.get("feature_names", [])
            if saved_features != FEATURE_NAMES:
                raise RuntimeError(
                    "模型特征顺序与当前 feature_extractor 不一致——"
                    "请重新训练 (python diagnosis/diagnose/training/train.py)"
                )
    return _BUNDLE


def _predict_verdict(
    visual: dict,
    functional: dict,
    performance: dict,
    page_type: str,
    page_state: Optional[dict],
) -> tuple[str, dict]:
    """返回 (verdict, debug_info)。"""
    bundle = _load_bundle()
    model = bundle["model"]

    feats = extract_features(visual, functional, performance, page_type, page_state)
    x = np.asarray([feats], dtype=float)

    pred = model.predict(x)[0]

    # 概率（决策树有 predict_proba）
    proba_map: dict = {}
    if hasattr(model, "predict_proba"):
        probs = model.predict_proba(x)[0]
        proba_map = {cls: float(p) for cls, p in zip(model.classes_, probs)}

    debug = {
        "features": {name: float(v) for name, v in zip(FEATURE_NAMES, feats)},
        "proba": proba_map,
        "model_version": "tree_v1",
    }
    return str(pred), debug


def run_triage_learned(
    image_bytes: bytes,
    page_type: str = "feed",
    fault_profile: str = "normal",
    page_state: dict = None,
    perf_data: dict = None,
    use_cascade: bool = False,
) -> dict:
    """与 rule_triage.run_triage 同接口，verdict 改用模型预测。

    其他子断言 (visual / functional / performance) 仍用规则法计算，
    因为它们既是模型输入特征，也是结果可解释性的来源。

    若 use_cascade=True，则视觉 oracle 用 cascade（规则 → MLLM）。
    """
    page_state = page_state or {}
    perf_data = perf_data or {}

    # 复用现有 oracle 实现，把它们的输出当作特征
    import cv2
    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if image is None:
        return rule_triage._error_result("无法解码图像")

    if use_cascade:
        visual = CascadeOracle().analyze(image_bytes, page_type)
    else:
        visual = rule_triage._run_visual_assertions(image, page_type)
    functional = rule_triage._run_functional_assertions(page_state, page_type)
    performance = rule_triage._run_performance_assertions(perf_data)

    verdict, debug = _predict_verdict(visual, functional, performance, page_type, page_state)

    explanation = _build_explanation(verdict, visual, functional, performance, debug)

    return {
        "visual": visual,
        "functional": functional,
        "performance": performance,
        "verdict": verdict,
        "explanation": explanation,
        "triage_meta": {
            "engine": "learned_tree_v1" + ("_cascade" if use_cascade else ""),
            "proba": debug["proba"],
        },
    }


def _build_explanation(verdict: str, visual: dict, functional: dict, performance: dict, debug: dict) -> str:
    parts = []
    proba = debug.get("proba", {})
    if proba:
        top = sorted(proba.items(), key=lambda kv: kv[1], reverse=True)[:2]
        parts.append("置信度: " + ", ".join(f"{k}={v:.2f}" for k, v in top))
    if visual.get("is_blur") or visual.get("black_white"):
        parts.append(f"视觉异常(blur={visual.get('blur_score')}, edge={visual.get('edge_density')})")
    if not performance.get("pass", True):
        parts.append(f"性能: {performance.get('reason', '')}")
    if not functional.get("pass", True):
        parts.append(f"功能: {functional.get('reason', '')}")
    return "; ".join(parts) if parts else "全部断言通过"


def is_available() -> bool:
    try:
        _load_bundle()
        return True
    except (FileNotFoundError, RuntimeError):
        return False
