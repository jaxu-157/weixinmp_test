"""截图稳定性等待器 —— WeReplay (FSE'23) 思路的启发式版本。

WeReplay 用 DL 模型 (P=92.1%, R=93.3%) 判断"页面是否已渲染完成"。
我们这里用一个无需训练的等价启发式：
    连续 N 次截图之间的 SSIM 都 > 阈值 (默认 0.985) 则认为稳定。

实测对 demo-uniapp 三页面足够好：
    - normal/stale_ui:  ~ 200-400ms 就稳定
    - slow_api:         ~ 1200-1500ms 后稳定（接口回来）
    - blur_image:       ~ 300ms 稳定（图片本身就是模糊的，但是稳定的）
    - layout_overlap:   ~ 500ms 稳定

调用者只需要提供一个 "snapshot_fn"——能返回当前页面截图 (np.ndarray, RGB) 的零参函数。
不绑定 Minium / Appium / 任何具体 driver。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict
from typing import Callable, List, Optional

import numpy as np

try:
    from skimage.metrics import structural_similarity as ssim
except ImportError as e:
    raise ImportError(
        "stability_wait 需要 scikit-image，请运行: pip install scikit-image"
    ) from e


@dataclass
class StabilityTrace:
    """每次截图稳定性等待的诊断追踪。"""
    wait_ms: int                 # 实际等待毫秒
    samples: int                 # 总共采样了几帧
    final_ssim: float            # 最后一帧与倒数第二帧 SSIM
    stable: bool                 # 是否在 max_wait_ms 内达到稳定
    ssim_history: List[float]    # 每相邻两帧 SSIM 历史
    timeout: bool                # 是否超时返回最后一帧

    def to_dict(self):
        return asdict(self)


def _to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    if img.shape[2] == 4:  # RGBA
        img = img[..., :3]
    return (0.299 * img[..., 0] + 0.587 * img[..., 1] + 0.114 * img[..., 2]).astype(np.uint8)


def _pair_ssim(a: np.ndarray, b: np.ndarray) -> float:
    """两帧间的 SSIM，归一化到 [0,1]。"""
    if a.shape != b.shape:
        # 尺寸不一致直接判定差异极大
        return 0.0
    ga = _to_gray(a)
    gb = _to_gray(b)
    try:
        score = ssim(ga, gb, data_range=255)
    except ValueError:
        # 太小的图像 SSIM 会抛错，fallback 用像素均方差
        diff = (ga.astype(np.float32) - gb.astype(np.float32)) ** 2
        score = 1.0 - min(1.0, diff.mean() / (255.0 ** 2))
    return float(max(0.0, min(1.0, score)))


def wait_until_stable(
    snapshot_fn: Callable[[], np.ndarray],
    max_wait_ms: int = 5000,
    poll_interval_ms: int = 200,
    ssim_threshold: float = 0.985,
    stable_window: int = 3,
    min_samples: int = 2,
) -> tuple[np.ndarray, StabilityTrace]:
    """等待 snapshot_fn 返回的画面稳定，再返回最终截图 + trace。

    算法：
        每 poll_interval_ms 取一帧；最近 stable_window-1 个相邻 SSIM 都 >= ssim_threshold
        则判定稳定。max_wait_ms 内未稳定返回最后一帧并标记 timeout。
    """
    assert stable_window >= 2, "stable_window 至少 2"
    assert min_samples >= 2, "min_samples 至少 2"

    t0 = time.time()
    frames: List[np.ndarray] = []
    ssims: List[float] = []

    # 取第一帧
    frames.append(snapshot_fn())

    while True:
        time.sleep(poll_interval_ms / 1000.0)
        frames.append(snapshot_fn())
        s = _pair_ssim(frames[-2], frames[-1])
        ssims.append(s)

        elapsed_ms = int((time.time() - t0) * 1000)
        # 至少采 min_samples 个相邻 SSIM 后才允许判定稳定
        if len(ssims) >= max(stable_window - 1, min_samples - 1):
            recent = ssims[-(stable_window - 1):]
            if all(x >= ssim_threshold for x in recent):
                return frames[-1], StabilityTrace(
                    wait_ms=elapsed_ms,
                    samples=len(frames),
                    final_ssim=float(s),
                    stable=True,
                    ssim_history=[round(x, 4) for x in ssims],
                    timeout=False,
                )

        if elapsed_ms >= max_wait_ms:
            return frames[-1], StabilityTrace(
                wait_ms=elapsed_ms,
                samples=len(frames),
                final_ssim=float(ssims[-1] if ssims else 0.0),
                stable=False,
                ssim_history=[round(x, 4) for x in ssims],
                timeout=True,
            )


def wait_from_files(
    take_screenshot_to: Callable[[str], None],
    tmp_dir: str,
    **kwargs,
) -> tuple[str, StabilityTrace]:
    """适配那些只能 "截图到磁盘文件" 的 driver（比如 Minium 的 app.screen_shot）。

    内部把 take_screenshot_to 包成 snapshot_fn(返回 ndarray)，最后只保留最终稳定那帧的 png。
    """
    import os
    import uuid
    from PIL import Image

    os.makedirs(tmp_dir, exist_ok=True)

    def _snap():
        p = os.path.join(tmp_dir, f"_probe_{uuid.uuid4().hex[:8]}.png")
        # 截图可能因 driver 未就绪失败；重试 3 次，每次 sleep 0.4s
        last_err = None
        for attempt in range(3):
            try:
                take_screenshot_to(p)
                if os.path.exists(p):
                    break
            except Exception as e:
                last_err = e
            time.sleep(0.4)
        if not os.path.exists(p):
            raise FileNotFoundError(
                f"截图重试 3 次仍失败: {p} (last_err={last_err})"
            )
        img = np.array(Image.open(p).convert("RGB"))
        # 探针文件马上删，避免污染目录
        try:
            os.remove(p)
        except OSError:
            pass
        return img

    final_arr, trace = wait_until_stable(_snap, **kwargs)
    out_path = os.path.join(tmp_dir, f"stable_{int(time.time() * 1000)}.png")
    Image.fromarray(final_arr).save(out_path)
    return out_path, trace


if __name__ == "__main__":
    # 自测：模拟"前 800ms 抖动，之后稳定"的场景
    import random

    base = np.zeros((480, 320, 3), dtype=np.uint8)
    base[:, :] = (200, 200, 200)
    base[100:200, 50:250] = (50, 50, 50)
    start = time.time()

    def fake_snap():
        elapsed = time.time() - start
        if elapsed < 0.8:
            jitter = np.random.randint(-20, 21, base.shape, dtype=np.int16)
            return np.clip(base.astype(np.int16) + jitter, 0, 255).astype(np.uint8)
        return base

    img, trace = wait_until_stable(fake_snap, poll_interval_ms=120, max_wait_ms=3000)
    print("=== self-test ===")
    print(f"stable={trace.stable}  wait_ms={trace.wait_ms}  samples={trace.samples}")
    print(f"final_ssim={trace.final_ssim:.4f}  history={trace.ssim_history}")
