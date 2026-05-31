"""Source-level fault catalog for the xtx (小兔鲜儿) home page.

Each mutation rewrites REAL third-party source to inject a COMMON developer
mistake whose ground-truth root-cause DIMENSION is known. Files are relative to
fault_bench/xtx/src. `old` must occur exactly once in the file.

Dimensions (coarse, matching Vision-Triage's triage axes):
  visual       -> render/appearance broken (missing image, invisible text, blur/blank)
  layout       -> geometry broken (overflow / overlap)  [folded into 'visual' for RCA]
  functional   -> wrong data rendered (undefined/NaN/[object Object], empty bindings)
  performance  -> slow to render / blocked main thread
"""

MUTATIONS = [
    # ---------------- VISUAL: render / appearance ----------------
    {
        "id": "guess_missing_image",
        "dim": "visual", "subtype": "missing_image",
        "file": "components/XtxGuess.vue",
        "old": ':src="item.picture"',
        "new": ':src="\'\'"',
        "note": "猜你喜欢商品图 src 绑定丢失（写错字段/忘了拼地址）→ 大面积缺图",
    },
    {
        "id": "swiper_missing_image",
        "dim": "visual", "subtype": "missing_image",
        "file": "components/XtxSwiper.vue",
        "old": ':src="item.imgUrl"',
        "new": ':src="\'\'"',
        "note": "首页轮播大图 src 丢失 → 顶部 banner 缺图",
    },
    {
        "id": "guess_invisible_text",
        "dim": "visual", "subtype": "low_contrast",
        "file": "components/XtxGuess.vue",
        "old": "color: #262626;\n    overflow: hidden;",
        "new": "color: #fdfdfd;\n    overflow: hidden;",
        "note": "商品名颜色写成近白色（在白卡片上）→ 文字不可见（对比度故障）",
    },

    # ---------------- LAYOUT: geometry (overflow/overlap) ----------------
    {
        "id": "guess_item_overflow",
        "dim": "layout", "subtype": "overflow",
        "file": "components/XtxGuess.vue",
        "old": "width: 345rpx;",
        "new": "width: 720rpx;",
        "note": "商品卡片宽度 345rpx→720rpx → 双列网格水平溢出",
    },
    {
        "id": "guess_image_oversize",
        "dim": "layout", "subtype": "overflow",
        "file": "components/XtxGuess.vue",
        "old": "width: 304rpx;",
        "new": "width: 900rpx;",
        "note": "商品图宽 304rpx→900rpx → 图片撑破卡片/网格",
    },
    {
        "id": "hot_cards_nowrap",
        "dim": "layout", "subtype": "overflow",
        "file": "pages/index/styles/hot.scss",
        "old": "flex-wrap: wrap;",
        "new": "flex-wrap: nowrap;",
        "note": "热门专区卡片去掉换行 → 多图挤在一行水平溢出",
    },
    {
        "id": "hot_image_oversize",
        "dim": "layout", "subtype": "overflow",
        "file": "pages/index/styles/hot.scss",
        "old": "width: 150rpx;",
        "new": "width: 760rpx;",
        "note": "热门专区图片 150rpx→760rpx → 撑破 50% 宽的面板格子",
    },

    # ---------------- FUNCTIONAL: wrong data rendered ----------------
    {
        "id": "guess_price_nan",
        "dim": "functional", "subtype": "data_mismatch",
        "file": "components/XtxGuess.vue",
        "old": "<text>{{ item.price }}</text>",
        "new": "<text>{{ item.price * item.count }}</text>",
        "note": "价格用了不存在的 item.count 参与计算 → 渲染 NaN（异步/字段错配）",
    },
    {
        "id": "guess_name_empty",
        "dim": "functional", "subtype": "data_mismatch",
        "file": "components/XtxGuess.vue",
        "old": "<view class=\"name\"> {{ item.name }} </view>",
        "new": "<view class=\"name\"> {{ item.title }} </view>",
        "note": "商品名绑定写错字段 item.title → 名称全空（字段错配，硬样本）",
    },

    # ---------------- PERFORMANCE: blocked render ----------------
    {
        "id": "guess_blocking_loop",
        "dim": "performance", "subtype": "main_thread_block",
        "file": "components/XtxGuess.vue",
        "old": "const pageParams: Required<PageParams> = {",
        "new": "const __t = Date.now(); while (Date.now() - __t < 1400) {}\nconst pageParams: Required<PageParams> = {",
        "note": "组件 setup 里同步死循环 1.4s（误写阻塞计算）→ 首页内容迟迟不出",
    },
]


def coarse_dim(dim: str) -> str:
    """Fold 'layout' into 'visual' for the 3-axis RCA scoring."""
    return "visual" if dim in ("visual", "layout") else dim
