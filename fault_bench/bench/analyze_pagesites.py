"""数据驱动：在为 cart/my 实现 page-aware 扩样本【之前】，先量化——
盲扫 cart/my 源码发现的变异点里，有多少落在【headless 实际渲染的(登出态)分支】？
落在 v-if="memberStore.profile" 等登录态分支的，注入后无视觉变化→会误判为漏检。
不臆断，先数。
"""
from __future__ import annotations
import os
import re
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
FB = os.path.abspath(os.path.join(HERE, ".."))
SRC = os.path.join(FB, "xtx", "src")

_IMG = re.compile(r':src="([^"]+)"')
_BIND = re.compile(r"\{\{\s*([a-zA-Z_][\w]*(?:\.[a-zA-Z_]\w*)+)\s*\}\}")
_WIDTH = re.compile(r"width:\s*(\d+)rpx")
_COLOR = re.compile(r"color:\s*(#[0-9a-fA-F]{6})")

FILES = {
    "my": ["pages/my/my.vue"],
    "cart": ["pages/cart/components/CartMain.vue", "pages/cart/cart.vue"],
}


def find_sites(s):
    sites = []
    for m in _IMG.finditer(s):
        if s.count(m.group(0)) == 1:
            sites.append(("img", m.group(0), m.start()))
    for m in _BIND.finditer(s):
        if s.count(m.group(0)) == 1:
            sites.append(("bind", m.group(0), m.start()))
    for m in _WIDTH.finditer(s):
        if int(m.group(1)) >= 40 and s.count(m.group(0)) == 1:
            sites.append(("width", m.group(0), m.start()))
    for m in _COLOR.finditer(s):
        if m.group(1).lower() not in ("#ffffff", "#fefefe", "#fdfdfd", "#fcfcfc") and s.count(m.group(0)) == 1:
            sites.append(("color", m.group(0), m.start()))
    return sites


def main():
    out = {}
    for page, files in FILES.items():
        page_sites = []
        for rel in files:
            fp = os.path.join(SRC, rel)
            if not os.path.exists(fp):
                continue
            s = open(fp, encoding="utf-8").read()
            sites = find_sites(s)
            # 判定每个站点是否在【登出态渲染区】：粗略——看它前面最近的 v-if/v-else 上下文
            # 登录态分支标志：v-if="memberStore.profile" / <template v-if="memberStore.profile">
            for kind, text, pos in sites:
                before = s[:pos]
                # 找最近的 overview/branch 标记
                in_login_required = False
                # template v-if profile ... </template> 区间，或 view v-if profile ... v-else
                vif = before.rfind('v-if="memberStore.profile"')
                velse = before.rfind("v-else")
                vif2 = before.rfind('v-if="showCartList"')
                if vif > velse:  # 最近的是 v-if profile（登录态），且其后还没到 v-else
                    in_login_required = True
                page_sites.append({"file": rel, "kind": kind, "text": text[:40],
                                   "likely_rendered_loggedout": not in_login_required})
        rendered = [x for x in page_sites if x["likely_rendered_loggedout"]]
        out[page] = {
            "total_sites": len(page_sites),
            "rendered_loggedout": len(rendered),
            "rendered_detail": rendered,
        }
    json.dump(out, open(os.path.join(FB, "campaign_out", "_pagesites.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    for page, d in out.items():
        print(f"{page}: total={d['total_sites']} rendered_loggedout={d['rendered_loggedout']}")


if __name__ == "__main__":
    main()
