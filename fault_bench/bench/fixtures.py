"""Canned responses for the (down) itheima backend used by xtx home page.

Envelope follows the app's `Data<T>` shape: {code, msg, result}.
Endpoints consumed by pages/index/index.vue + XtxGuess.vue:
  GET /home/banner            -> result: BannerItem[]
  GET /home/category/mutli    -> result: CategoryItem[]
  GET /home/hot/mutli         -> result: HotItem[]
  GET /home/goods/guessLike   -> result: PageResult<GuessItem>
"""
from __future__ import annotations

from . import images


def _envelope(result):
    return {"code": "1", "msg": "ok", "result": result}


def banner_fixture(n=3):
    return _envelope([
        {"id": f"b{i}", "imgUrl": images.banner(i), "hrefUrl": "", "type": 1}
        for i in range(n)
    ])


CATEGORY_NAMES = ["手机数码", "美妆护肤", "家居日用", "服饰鞋包", "母婴亲子",
                  "运动户外", "粮油生鲜", "图书音像", "汽车用品", "家用电器"]


def category_fixture():
    return _envelope([
        {"id": f"c{i}", "name": CATEGORY_NAMES[i], "icon": images.category_icon(i)}
        for i in range(len(CATEGORY_NAMES))
    ])


def hot_fixture():
    panels = [
        ("特惠推荐", "精选全网精品好货"),
        ("爆款推荐", "最受欢迎的好物"),
        ("一站买全", "买点好的，犒赏自己"),
        ("新鲜好物", "新品尝鲜"),
    ]
    out = []
    for i, (title, alt) in enumerate(panels):
        out.append({
            "id": f"h{i}", "title": title, "alt": alt, "type": str(i + 1), "target": "",
            "pictures": [images.hot_picture(i * 2), images.hot_picture(i * 2 + 1)],
        })
    return _envelope(out)


GUESS_NAMES = [
    "云珍·轻软细腻面巾纸", "梵想·便携充电宝 10000mAh", "简约纯棉短袖T恤",
    "北欧风陶瓷马克杯", "无线蓝牙降噪耳机", "多功能厨房收纳架",
    "保湿补水面膜 10片", "运动速干跑步鞋",
]


def guess_fixture(page=1, page_size=10):
    items = [
        {"id": f"g{i}", "name": GUESS_NAMES[i % len(GUESS_NAMES)],
         "price": round(19 + i * 17.5, 2), "picture": images.guess_picture(i)}
        for i in range(8)
    ]
    return _envelope({"items": items, "counts": len(items),
                      "page": page, "pages": 1, "pageSize": page_size})


def route_table():
    """Substring -> response builder. Order matters (most specific first)."""
    return [
        ("/home/banner", lambda: banner_fixture()),
        ("/home/category/mutli", lambda: category_fixture()),
        ("/home/hot/mutli", lambda: hot_fixture()),
        ("/home/goods/guessLike", lambda: guess_fixture()),
    ]
