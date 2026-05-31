"""随机源码变异生成器 —— 扫描小兔鲜儿(xtx)首页相关源码，自动发现可变异点，
为每个点生成已知根因维度的损坏变体。比手写固定列表更无偏、样本更大。

随机性：种子可复现地打乱顺序 + 对每个站点的损坏变体做种子选择；
覆盖是穷举所有可发现站点（无抽样偏差），bootstrap CI 给检出率的不确定性。

每个变异：{id, dim, file, old, new}，old 在目标文件中 count==1（生成时已校验）。
维度：visual（缺图/低对比度/溢出，溢出按 RCA 折叠进 visual）、functional（字段错配→空/NaN）。
"""
from __future__ import annotations
import os
import re
import random

# 首页渲染会展示这些文件的内容（renderer 抓 "/" = pages/index/index）
HOME_FILES = [
    "components/XtxSwiper.vue",
    "components/XtxGuess.vue",
    "pages/index/components/CategoryPanel.vue",
    "pages/index/components/HotPanel.vue",
    "pages/index/components/CustomNavbar.vue",
    "pages/index/index.vue",
    "pages/index/styles/category.scss",
    "pages/index/styles/hot.scss",
    "components/styles/XtxSwiper.scss",
    "components/XtxGuess.vue",  # 其 <style> 段含 width/color
]

# Page-aware 扩样本（R3）：探针 + analyze_pagesites 实测确定可注入页。
#   - "my" 页 headless 只渲染【登出态】，故跳过含 memberStore.profile 的登录态分支站点
#     （注入那里无视觉变化→会误判漏检）。实测保留 6 个真实可渲染站点。
#   - "cart" 页排除：CartMain 的购物车列表/空态全在 v-if=memberStore.profile / showCartList
#     登录态分支，登出态唯一渲染的是共享 XtxGuess（已计入 index）→ 盲扫 0 个独有可注入站点。
# 每页：{files: [...], skip: [子串黑名单], route, wait_selector}。index 保持原样（A 线数字不变）。
PAGE_SPEC = {
    "index": {"files": HOME_FILES, "skip": [],
              "route": "", "wait_selector": ".guess-item"},
    "my": {"files": ["pages/my/my.vue"], "skip": ["memberStore.profile"],
           "route": "pages/my/my", "wait_selector": ".guess-item"},
}

_IMG = re.compile(r':src="([^"]+)"')
_BIND = re.compile(r"\{\{\s*([a-zA-Z_][\w]*(?:\.[a-zA-Z_]\w*)+)\s*\}\}")  # item.xxx 形
_WIDTH = re.compile(r"width:\s*(\d+)rpx")
_COLOR = re.compile(r"color:\s*(#[0-9a-fA-F]{6})")


def _unique(text: str, sub: str) -> bool:
    return text.count(sub) == 1


def discover(src_root: str, files: list | None = None,
             page: str = "index", skip: list | None = None) -> list[dict]:
    """扫描指定页的文件，穷举所有 count==1 的可变异站点 × 损坏变体。
    每个变异打 page 标签；old 含 skip 中任一子串的站点被剔除（登录态死分支）。"""
    files = files if files is not None else HOME_FILES
    skip = skip or []
    muts = []
    seen_files = set()
    for rel in files:
        if rel in seen_files:
            continue
        seen_files.add(rel)
        fp = os.path.join(src_root, rel)
        if not os.path.exists(fp):
            continue
        s = open(fp, encoding="utf-8").read()

        # --- visual / missing_image ---
        for m in _IMG.finditer(s):
            old = m.group(0)
            if not _unique(s, old):
                continue
            muts.append({"id": f"img@{_short(rel)}:{m.group(1)[:12]}",
                         "dim": "visual", "subtype": "missing_image",
                         "file": rel, "old": old, "new": ':src="\'\'"'})

        # --- visual / low_contrast（颜色改近白；跳过本就近白的）---
        for m in _COLOR.finditer(s):
            old = m.group(0)
            hexv = m.group(1).lower()
            if hexv in ("#ffffff", "#fefefe", "#fdfdfd", "#fcfcfc"):
                continue
            if not _unique(s, old):
                continue
            muts.append({"id": f"color@{_short(rel)}:{hexv}",
                         "dim": "visual", "subtype": "low_contrast",
                         "file": rel, "old": old, "new": "color: #fcfcfc"})

        # --- visual(layout) / overflow（宽度放大；两个倍数变体）---
        for m in _WIDTH.finditer(s):
            old = m.group(0)
            val = int(m.group(1))
            if val < 40:  # 太小的宽度放大也不易溢出，跳过
                continue
            if not _unique(s, old):
                continue
            for factor, tag in ((6, "x6"),):
                new = f"width: {val * factor}rpx"
                muts.append({"id": f"width@{_short(rel)}:{val}{tag}",
                             "dim": "layout", "subtype": "overflow",
                             "file": rel, "old": old, "new": new})

        # --- functional / data_mismatch（绑定字段改错→空或 undefined）---
        for m in _BIND.finditer(s):
            old = m.group(0)
            field = m.group(1)
            if not _unique(s, old):
                continue
            # 变体1：字段尾加 ZZ → 取不到值 → 空绑定
            new1 = old.replace(field, field + "ZZ")
            muts.append({"id": f"bindempty@{_short(rel)}:{field}",
                         "dim": "functional", "subtype": "empty_binding",
                         "file": rel, "old": old, "new": new1})
    # 注：性能故障(onLoad 同步阻塞)不纳入本生成器——实测 H5 零侵入墙钟/Long Task 通道
    # 检测不可靠（同一注入 delta 1359ms vs 172ms 不可复现），性能维仍是 H5 路径盲区，见 FINAL_REPORT §2.5。
    # 打 page 标签 + 剔除死分支站点（id 也带 page 前缀以免跨页 id 撞车）。
    tagged = []
    for m in muts:
        if any(k in m["old"] for k in skip):
            continue
        m = {**m, "page": page, "id": (m["id"] if page == "index" else f"{page}/{m['id']}")}
        tagged.append(m)
    return tagged


def _short(rel: str) -> str:
    return os.path.splitext(os.path.basename(rel))[0]


def generate(src_root: str, seed: int = 42, limit: int | None = None,
             pages: list | None = None) -> list[dict]:
    """跨页穷举变异。pages=None → 全部 PAGE_SPEC；传 ["index"] 复现旧 A 线(20变异,数字不变)。"""
    page_keys = pages if pages is not None else list(PAGE_SPEC.keys())
    muts = []
    for pk in page_keys:
        spec = PAGE_SPEC[pk]
        muts += discover(src_root, files=spec["files"], page=pk, skip=spec["skip"])
    rng = random.Random(seed)
    rng.shuffle(muts)            # 随机顺序（可复现）
    seen, out = set(), []
    for m in muts:
        if m["id"] in seen:
            continue
        seen.add(m["id"])
        out.append(m)
    if limit:
        out = out[:limit]
    return out


if __name__ == "__main__":
    import sys, json
    root = sys.argv[1] if len(sys.argv) > 1 else r"D:\weixinmp_test\fault_bench\xtx\src"
    ms = generate(root)
    from collections import Counter
    print(f"discovered {len(ms)} mutations")
    print("by dim:", dict(Counter(m["dim"] for m in ms)))
    for m in ms:
        print(f"  {m['dim']:11s} {m['subtype']:14s} {m['file']:42s} | {m['old'][:40]} -> {m['new'][:30]}")
