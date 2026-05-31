"""根因定位(确定性,无 LLM)—— 把"检出"升级为"定位到源文件/字段"。

设计(基于第0步 DOM 探测的实测结论):
  - H5 prod 构建里 Vue per-node 实例不可达(__vue__ 为空),但:
    * data-v-* scoped 属性可达(167/368 元素带),每个 hash 对应一个 .vue
    * 元素 class 可达,且大量 class 在源码里【唯一】属于某个 .vue 的 <style>
  - 故确定性定位链:worst tile → elementsFromPoint(中心) → 元素 class/data-v
    → class→file 索引 → 源文件。字段名再从该文件模板里的 {{ }} 绑定取。

本模块提供:
  - build_class_file_index(src_root): 扫描所有 .vue,产出 {class_name: [files...]}
    （只保留某 class 唯一出现的文件作强定位;多文件出现的弱化）
  - tile_to_pixelbox(i, j): tile 坐标 → 像素框中心(视口 375x2200, 8x3)
  - localize_visual(elements_at_points, class_index): 元素栈 → 预测源文件 + 证据
"""
from __future__ import annotations
import os
import re

VIEWPORT_W, VIEWPORT_H = 375, 2200
TILE_ROWS, TILE_COLS = 8, 3

# 提取 <style> 段里的 class 选择器 .xxx  和 模板里的 class="a b c"
_STYLE_CLASS = re.compile(r"\.([a-zA-Z_][\w-]*)")
_TPL_CLASS = re.compile(r'class="([^"]+)"')


def _iter_vue(src_root: str):
    for dp, _, fns in os.walk(src_root):
        for fn in fns:
            if fn.endswith(".vue"):
                yield os.path.join(dp, fn)


def build_class_file_index(src_root: str) -> dict:
    """{class_name: sorted([rel_file...])}。只扫 <style> 选择器(最能指认组件归属)。"""
    idx: dict[str, set] = {}
    for fp in _iter_vue(src_root):
        rel = os.path.relpath(fp, src_root).replace("\\", "/")
        s = open(fp, encoding="utf-8").read()
        style = s[s.find("<style"):] if "<style" in s else ""
        classes = set(_STYLE_CLASS.findall(style))
        # 也并入模板 class(覆盖只在模板写、样式在别处的情况)
        tpl = s[s.find("<template>"):s.find("</template>")] if "<template>" in s else ""
        for grp in _TPL_CLASS.findall(tpl):
            classes.update(grp.split())
        for c in classes:
            idx.setdefault(c, set()).add(rel)
    # uni-app / 框架通用 class 噪声过滤(出现在过多文件的不作定位锚)
    noise = {"item", "image", "name", "price", "text", "navigator", "title", "icon", "card", "cards"}
    return {c: sorted(fs) for c, fs in idx.items() if c not in noise}


_CSS_HASH_CLASS = re.compile(r"\.([a-zA-Z_][\w-]*)\[data-v-([0-9a-f]{8})\]")
# uni-app/框架通用类:不作为组件判别依据(出现在多个组件)
_NOISE_CLASSES = {"item", "image", "name", "price", "text", "navigator", "title",
                  "icon", "card", "cards", "meta", "panel", "forEach", "wrap"}


def build_hash_file_index(src_root: str, dist_css_dir: str) -> dict:
    """data-v hash → .vue 源文件（修法核心：hash 每个 .vue 唯一，不像 class 会撞车）。

    做法：dist 的 scoped CSS 里选择器形如 `.cls[data-v-HASH]` → 得 {hash: {classes}}；
    再与每个 .vue 的 <style> 类集做"判别类"(去框架噪声)重叠打分，hash 归到重叠最高的 .vue。
    """
    # 1) hash → CSS 里挂的 class 集
    hash_cls: dict[str, set] = {}
    for fp in (os.path.join(dist_css_dir, f) for f in os.listdir(dist_css_dir)
               if f.endswith(".css")) if os.path.isdir(dist_css_dir) else []:
        s = open(fp, encoding="utf-8", errors="replace").read()
        for cls, h in _CSS_HASH_CLASS.findall(s):
            hash_cls.setdefault(h, set()).add(cls)
    # 2) .vue → 类集 = 模板 class="..." ∪ <style> 选择器
    #    （很多组件样式在外部 .scss，<style> 为空，故必须并入模板 class 才能匹配上）
    file_cls: dict[str, set] = {}
    for fp in _iter_vue(src_root):
        rel = os.path.relpath(fp, src_root).replace("\\", "/")
        s = open(fp, encoding="utf-8").read()
        cls: set = set()
        tpl = s[s.find("<template>"):s.find("</template>")] if "<template>" in s else ""
        for grp in _TPL_CLASS.findall(tpl):
            cls.update(grp.split())
        style = s[s.find("<style"):] if "<style" in s else ""
        cls.update(_STYLE_CLASS.findall(style))
        file_cls[rel] = cls
    # 3) hash → 最佳 .vue（按判别类重叠数；并列则取重叠/文件类集占比高者）
    out = {}
    for h, hcs in hash_cls.items():
        disc = hcs - _NOISE_CLASSES
        best, best_score = None, 0.0
        for rel, fcs in file_cls.items():
            inter = len(disc & (fcs - _NOISE_CLASSES))
            if inter == 0:
                continue
            score = inter + inter / (len(fcs - _NOISE_CLASSES) + 1)  # 重叠数为主,占比微调
            if score > best_score:
                best, best_score = rel, score
        if best:
            out[h] = best
    return out


def localize_by_datav(stack: list, hash_index: dict) -> dict:
    """元素栈 → 源文件：自顶向下取第一个 data-v hash 能在 hash_index 命中的元素。"""
    for el in stack:
        for dv in (el.get("dataV") or []):
            h = dv.replace("data-v-", "")
            if h in hash_index:
                return {"file": hash_index[h], "data_v": dv,
                        "anchor_class": (el.get("cls") or "").split()[:1],
                        "confidence": "high", "via": "data_v_hash"}
    return {"file": None, "data_v": [], "anchor_class": None,
            "confidence": "none", "via": "no_hash"}


def tile_center_px(i: int, j: int) -> tuple[int, int]:
    """tile (row i, col j) → 像素中心 (x, y)。"""
    x = j * VIEWPORT_W // TILE_COLS + (VIEWPORT_W // TILE_COLS) // 2
    y = i * VIEWPORT_H // TILE_ROWS + (VIEWPORT_H // TILE_ROWS) // 2
    return x, y


def _rect_inter_area(r, box) -> float:
    """元素 rect {x,y,w,h} 与 tile box {x,y,w,h} 的交叠面积。"""
    ax1, ay1 = r["x"], r["y"]
    ax2, ay2 = r["x"] + r["w"], r["y"] + r["h"]
    bx1, by1 = box["x"], box["y"]
    bx2, by2 = box["x"] + box["w"], box["y"] + box["h"]
    ix = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0.0, min(ay2, by2) - max(ay1, by1))
    return ix * iy


def localize_by_bbox_area(elements: list, worst_boxes: list, hash_index: dict,
                          max_elem_frac: float = 0.6) -> dict:
    """bbox 面积排序定位(替代单点采样)：
    在【所有带 data-v hash 且 hash 能映射到文件】的元素里，挑与 worst tiles 交叠面积最大的；
    排除视口占比 > max_elem_frac 的根容器(否则大容器总赢)。
    elements: [{rect:{x,y,w,h}, dataV:[...], cls}], worst_boxes: [{x,y,w,h}, ...]
    """
    viewport_area = VIEWPORT_W * VIEWPORT_H
    best, best_area = None, 0.0
    for el in elements:
        r = el.get("rect")
        if not r or r["w"] <= 0 or r["h"] <= 0:
            continue
        # 该元素 hash 是否可映射
        fpath = None
        dvs = el.get("dataV") or []
        for dv in dvs:
            h = dv.replace("data-v-", "")
            if h in hash_index:
                fpath = hash_index[h]; dv_hit = dv; break
        if not fpath:
            continue
        if (r["w"] * r["h"]) > max_elem_frac * viewport_area:  # 跳过根容器
            continue
        area = sum(_rect_inter_area(r, b) for b in worst_boxes)
        if area > best_area:
            best, best_area = {"file": fpath, "data_v": dv_hit,
                               "anchor_class": (el.get("cls") or "").split()[:1],
                               "confidence": "high", "via": "bbox_area",
                               "inter_area": round(area, 1)}, area
    return best or {"file": None, "data_v": [], "anchor_class": None,
                    "confidence": "none", "via": "no_bbox_hit"}


def tile_box_px(i: int, j: int) -> dict:
    return {"x": j * VIEWPORT_W // TILE_COLS, "y": i * VIEWPORT_H // TILE_ROWS,
            "w": VIEWPORT_W // TILE_COLS, "h": VIEWPORT_H // TILE_ROWS}


def localize_from_elements(stack: list, class_index: dict) -> dict:
    """给定一个 elementsFromPoint 返回的元素栈(每项 {cls, dataV, tag, text}),
    返回 {file, anchor_class, data_v, confidence}。
    策略:自顶向下找第一个 class 能在 class_index 唯一命中文件的元素。"""
    best = None
    for el in stack:
        cls = (el.get("cls") or "").strip()
        for c in cls.split():
            files = class_index.get(c)
            if files and len(files) == 1:
                return {"file": files[0], "anchor_class": c,
                        "data_v": el.get("dataV") or [], "confidence": "high",
                        "via": "unique_class"}
            if files and best is None:
                best = {"file": files[0], "anchor_class": c, "data_v": el.get("dataV") or [],
                        "confidence": "low", "via": f"ambiguous_class({len(files)} files)"}
    # 退化:用 data-v hash(至少指认是某个组件,即便不知文件名)
    if best is None:
        for el in stack:
            dv = el.get("dataV") or []
            if dv:
                return {"file": None, "anchor_class": (el.get("cls") or "").split()[:1],
                        "data_v": dv, "confidence": "component_only", "via": "data_v_hash"}
    return best or {"file": None, "anchor_class": None, "data_v": [], "confidence": "none", "via": "no_anchor"}


if __name__ == "__main__":
    import json, sys
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "xtx", "src")
    idx = build_class_file_index(root)
    # 验证:观测到的关键 class 能否唯一定位
    checks = ["guess-item", "guess", "caption", "category", "navbar", "panel", "cards", "scroll-view"]
    out = {"n_classes": len(idx),
           "checks": {c: idx.get(c, "MISSING") for c in checks}}
    print(json.dumps(out, ensure_ascii=False, indent=2))
