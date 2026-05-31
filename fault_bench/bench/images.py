"""Deterministic, content-rich placeholder images as data-URIs.

We fixture the (down) itheima backend with LOCAL data-URI images so the real
xtx UI renders deterministically and offline. Images are intentionally
texture-rich (gradient + shapes + text) so a HEALTHY render has high edge
density / sharpness — otherwise the diagnosis pipeline could mistake a flat
placeholder for a blank/blurry page.
"""
from __future__ import annotations

import base64
import io

from PIL import Image, ImageDraw, ImageFont


def _font(sz: int):
    try:
        return ImageFont.truetype("arial.ttf", sz)
    except Exception:
        return ImageFont.load_default()


def _data_uri(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def make_image(w: int, h: int, c1, c2, label: str, seed: int = 0) -> str:
    """Gradient background + grid lines + a couple shapes + label text."""
    img = Image.new("RGB", (w, h), c1)
    px = img.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        r = int(c1[0] * (1 - t) + c2[0] * t)
        g = int(c1[1] * (1 - t) + c2[1] * t)
        b = int(c1[2] * (1 - t) + c2[2] * t)
        for x in range(w):
            px[x, y] = (r, g, b)
    d = ImageDraw.Draw(img)
    # texture: grid + diagonal + circle (adds edges so it's not "blank/blurry")
    step = max(8, w // 8)
    for x in range(0, w, step):
        d.line([(x, 0), (x, h)], fill=(255, 255, 255), width=1)
    for y in range(0, h, step):
        d.line([(0, y), (w, y)], fill=(255, 255, 255), width=1)
    d.ellipse([w * 0.6, h * 0.55, w * 0.95, h * 0.95], outline=(255, 255, 255), width=3)
    d.rectangle([w * 0.05, h * 0.1, w * 0.45, h * 0.45], outline=(20, 20, 20), width=2)
    d.text((6, 6), label, fill=(20, 20, 20), font=_font(max(12, h // 6)))
    return _data_uri(img)


# distinct palettes
_PALS = [
    ((74, 144, 217), (30, 60, 120)),
    ((80, 176, 106), (20, 90, 50)),
    ((217, 160, 74), (120, 80, 20)),
    ((154, 74, 217), (70, 20, 110)),
    ((217, 74, 90), (120, 20, 40)),
    ((74, 200, 200), (20, 90, 90)),
]


def banner(i: int) -> str:
    c1, c2 = _PALS[i % len(_PALS)]
    return make_image(700, 280, c1, c2, f"BANNER {i+1}")


def category_icon(i: int) -> str:
    c1, c2 = _PALS[i % len(_PALS)]
    return make_image(120, 120, c1, c2, f"C{i+1}")


def hot_picture(i: int) -> str:
    c1, c2 = _PALS[i % len(_PALS)]
    return make_image(300, 300, c1, c2, f"HOT{i+1}")


def guess_picture(i: int) -> str:
    c1, c2 = _PALS[i % len(_PALS)]
    return make_image(320, 320, c1, c2, f"G{i+1}")
