"""SSIM + pHash 基线回归对比。

用途：
    给每个 (page) 在 normal profile 下先建一张基线截图；
    后续故障 profile 的截图与之对比，得到：
      - ssim:               结构相似度 [0,1]，越大越像
      - pixel_diff_ratio:   差异像素占比 [0,1]
      - phash_hamming:      pHash 汉明距离 (0-64)
      - mean_pixel_diff:    平均像素差 (0-255)
    并可选输出一张三联可视化对比图 (baseline | current | diff_heatmap)。

这是工业级回归测试做法（Applitools / Percy 都用类似 SSIM/pHash 组合）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from typing import Optional

import numpy as np
from PIL import Image

try:
    from skimage.metrics import structural_similarity as ssim
except ImportError as e:
    raise ImportError("baseline_compare 需要 scikit-image: pip install scikit-image") from e


@dataclass
class BaselineDiff:
    ssim: float
    pixel_diff_ratio: float
    mean_pixel_diff: float
    phash_hamming: int
    width: int
    height: int
    baseline_path: Optional[str] = None
    current_path: Optional[str] = None
    diff_path: Optional[str] = None

    def to_dict(self):
        return asdict(self)

    @property
    def is_regression(self) -> bool:
        """经验阈值：SSIM<0.92 或 像素差占比>0.05 视为视觉回归。"""
        return self.ssim < 0.92 or self.pixel_diff_ratio > 0.05


def _load(p_or_arr) -> np.ndarray:
    if isinstance(p_or_arr, np.ndarray):
        return p_or_arr
    return np.array(Image.open(p_or_arr).convert("RGB"))


def _to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    return (0.299 * img[..., 0] + 0.587 * img[..., 1] + 0.114 * img[..., 2]).astype(np.uint8)


def _resize_to_match(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """两张图尺寸不一致时统一缩到较小的那张。"""
    h = min(a.shape[0], b.shape[0])
    w = min(a.shape[1], b.shape[1])
    if a.shape[:2] != (h, w):
        a = np.array(Image.fromarray(a).resize((w, h), Image.BILINEAR))
    if b.shape[:2] != (h, w):
        b = np.array(Image.fromarray(b).resize((w, h), Image.BILINEAR))
    return a, b


def _phash(img: np.ndarray, hash_size: int = 8) -> np.ndarray:
    """简版感知哈希：32x32 DCT 取低频 8x8 平均阈值。"""
    gray = _to_gray(img)
    img_small = np.array(
        Image.fromarray(gray).resize((hash_size * 4, hash_size * 4), Image.BILINEAR),
        dtype=np.float32,
    )
    # 用 DCT 替代品：取 FFT 实部低频块，足够稳定
    dct = np.fft.fft2(img_small).real
    block = dct[:hash_size, :hash_size]
    med = np.median(block)
    return (block > med).astype(np.uint8).flatten()


def _hamming(a: np.ndarray, b: np.ndarray) -> int:
    return int(np.sum(a != b))


def compare_to_baseline(
    current,
    baseline,
    diff_out_path: Optional[str] = None,
    pixel_diff_threshold: int = 25,
) -> BaselineDiff:
    """对比 current 与 baseline，可选输出三联可视化图。

    current / baseline 可以是路径字符串或 np.ndarray。
    pixel_diff_threshold: 单像素 L1 差 > 此值才计入差异像素。
    """
    cur_path = current if isinstance(current, str) else None
    base_path = baseline if isinstance(baseline, str) else None

    cur = _load(current)
    base = _load(baseline)
    cur, base = _resize_to_match(cur, base)

    h, w = cur.shape[:2]
    cur_gray = _to_gray(cur)
    base_gray = _to_gray(base)
    s = float(ssim(base_gray, cur_gray, data_range=255))

    # 像素差
    diff = np.abs(cur.astype(np.int16) - base.astype(np.int16)).max(axis=2)
    diff_mask = diff > pixel_diff_threshold
    pixel_diff_ratio = float(diff_mask.mean())
    mean_pixel_diff = float(diff.mean())

    # pHash
    ham = _hamming(_phash(cur), _phash(base))

    # 可视化
    diff_path = None
    if diff_out_path is not None:
        os.makedirs(os.path.dirname(diff_out_path) or ".", exist_ok=True)
        # 三联图：baseline | current | heatmap
        heatmap = np.zeros_like(cur)
        red = diff_mask.astype(np.uint8) * 255
        heatmap[..., 0] = red                            # 红色：差异像素
        heatmap[..., 1] = (cur_gray // 2).astype(np.uint8)
        heatmap[..., 2] = (cur_gray // 2).astype(np.uint8)
        gap = np.ones((h, 4, 3), dtype=np.uint8) * 255
        triplet = np.concatenate([base, gap, cur, gap, heatmap], axis=1)
        Image.fromarray(triplet).save(diff_out_path)
        diff_path = diff_out_path

    return BaselineDiff(
        ssim=round(s, 4),
        pixel_diff_ratio=round(pixel_diff_ratio, 4),
        mean_pixel_diff=round(mean_pixel_diff, 2),
        phash_hamming=ham,
        width=w,
        height=h,
        baseline_path=base_path,
        current_path=cur_path,
        diff_path=diff_path,
    )


class BaselineStore:
    """简易基线存储：按 page 名管理基线截图文件。"""

    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

    def baseline_path(self, page: str) -> str:
        return os.path.join(self.base_dir, f"{page}.png")

    def has_baseline(self, page: str) -> bool:
        return os.path.exists(self.baseline_path(page))

    def save_baseline(self, page: str, src_path: str) -> str:
        from shutil import copy2
        dst = self.baseline_path(page)
        copy2(src_path, dst)
        return dst

    def diff(self, page: str, current_path: str, diff_out_dir: Optional[str] = None) -> Optional[BaselineDiff]:
        if not self.has_baseline(page):
            return None
        out = None
        if diff_out_dir:
            os.makedirs(diff_out_dir, exist_ok=True)
            out = os.path.join(diff_out_dir, f"{page}_diff.png")
        return compare_to_baseline(current_path, self.baseline_path(page), out)


if __name__ == "__main__":
    # 自测：人工构造一张基线 + 三种"扰动版"
    np.random.seed(0)
    h, w = 240, 160
    baseline = np.zeros((h, w, 3), dtype=np.uint8)
    baseline[:, :] = (220, 220, 220)
    baseline[40:120, 20:140] = (40, 100, 180)
    baseline[140:200, 20:140] = (80, 80, 80)

    cases = {
        "identical": baseline.copy(),
        "minor_noise": np.clip(baseline.astype(np.int16) + np.random.randint(-10, 11, baseline.shape, dtype=np.int16), 0, 255).astype(np.uint8),
        "blur_image": np.array(Image.fromarray(baseline).resize((w // 4, h // 4)).resize((w, h))),
        "layout_shift": np.roll(baseline, 30, axis=1),
        "fully_different": np.random.randint(0, 256, baseline.shape, dtype=np.uint8),
    }

    print(f"{'case':<20}{'ssim':<8}{'pix_diff':<10}{'mean_diff':<11}{'phash_ham':<10}{'regression?'}")
    print("-" * 70)
    for name, img in cases.items():
        d = compare_to_baseline(img, baseline)
        print(f"{name:<20}{d.ssim:<8.3f}{d.pixel_diff_ratio:<10.3f}"
              f"{d.mean_pixel_diff:<11.2f}{d.phash_hamming:<10}{d.is_regression}")
