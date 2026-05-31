"""真实原生 WXML 小程序（third-youzouzou-wxapp）源码变异目录。

全部标记基于**真实读过的源码文件**确定（2026-05-31），每个 old 在目标文件中 count==1。
可逆：runner 用二进制备份+finally 写回，保证字节级还原（youzouzou 在 .gitignore，不靠 git）。

维度（与 triage 三轴对齐）：visual / layout(RCA 折叠进 visual) / functional / performance
被测页：
  - others   = /pages/others/others（入口 tabBar，渲染 data.list 的 {{item.name}}）
  - pictures = /pages/others/pictures/pictures（本地图 example0-4.png，5 个图片框）
"""

MUTATIONS = [
    # ---------------- VISUAL: 缺图 ----------------
    {
        "id": "pictures_missing_image",
        "dim": "visual", "subtype": "missing_image",
        "page": "pictures", "page_path": "/pages/others/pictures/pictures",
        "file": "pages/others/pictures/pictures.js",
        "old": "activePic: '/images/example0.png',",
        "new": "activePic: '',",
        "note": "首图 src 置空（onShow 复制到全部5框）→ 整页图片缺失",
    },
    # ---------------- VISUAL: 不可见文字（低对比度）----------------
    {
        "id": "others_invisible_title",
        "dim": "visual", "subtype": "low_contrast",
        "page": "others", "page_path": "/pages/others/others",
        "file": "app.wxss",
        "old": ".page__title {\n  text-align: left;\n  font-size: 20px;\n  font-weight: 400;\n}",
        "new": ".page__title {\n  text-align: left;\n  font-size: 20px;\n  font-weight: 400;\n  color: #fbfbfb;\n}",
        "note": "页标题色改近白（白底上）→ '自定义组件' 不可见（对比度故障）",
    },
    # ---------------- LAYOUT: 横向溢出（RCA 折叠进 visual）----------------
    {
        "id": "pictures_box_overflow",
        "dim": "layout", "subtype": "overflow",
        "page": "pictures", "page_path": "/pages/others/pictures/pictures",
        "file": "pages/others/pictures/pictures.wxss",
        # 真实 wxss：.imgs_container{ width:100%; margin:...; overflow:hidden }
        # 注入：宽度撑到 1500rpx(>750视口) 且去掉 overflow:hidden（否则溢出被裁不外显）→ 横向溢出
        "old": ".imgs_container {\n  width: 100%;\n  margin: 20rpx 0 40rpx 0;\n  overflow: hidden;\n}",
        "new": ".imgs_container {\n  width: 1500rpx;\n  margin: 20rpx 0 40rpx 0;\n  overflow: visible;\n}",
        "note": "图片容器宽 100%→1500rpx + overflow:hidden→visible → 横向溢出(devtools scrollWidth>clientWidth)",
    },
    # ---------------- FUNCTIONAL: 数据 undefined（已最小验证过）----------------
    {
        "id": "others_data_undefined",
        "dim": "functional", "subtype": "data_mismatch",
        "page": "others", "page_path": "/pages/others/others",
        "file": "pages/others/others.js",
        "old": "name: '表单',",
        "new": "name: '表单' + undefined,",
        "note": "字符串拼接未处理 undefined → 渲染'表单undefined'+page.data 出 undefined token",
    },
    # ---------------- VISUAL: 按钮文字不可见（低对比度，扩样本）----------------
    {
        "id": "pictures_btn_invisible",
        "dim": "visual", "subtype": "low_contrast",
        "page": "pictures", "page_path": "/pages/others/pictures/pictures",
        "file": "pages/others/pictures/pictures.wxss",
        # 真实 .btn{ background:#6ed4bd; color:#fff } → 把文字色改成与背景同色 → 按钮文字不可见
        "old": "  color: #fff;\n  display: inline-block;",
        "new": "  color: #6ed4bd;\n  display: inline-block;",
        "note": "按钮文字色改成与背景(#6ed4bd)同色 → '上一张/下一张'文字不可见（对比度故障）",
    },
    # ---------------- FUNCTIONAL: 渲染 undefined（扩样本）----------------
    {
        "id": "pictures_length_undefined",
        "dim": "functional", "subtype": "data_mismatch",
        "page": "pictures", "page_path": "/pages/others/pictures/pictures",
        "file": "pages/others/pictures/pictures.js",
        # onShow 里 length 取了不存在的属性 → 渲染 "1 / undefined"（page.data.length=undefined token）
        "old": "length: this.data.imgs.length,",
        "new": "length: this.data.imgs.lengthX,",
        "note": "length 取不存在属性 imgs.lengthX → 页码渲染'1 / undefined'（page.data 出 undefined token）",
    },
    # ---------------- PERFORMANCE: 主线程阻塞 ----------------
    {
        "id": "pictures_blocking_loop",
        "dim": "performance", "subtype": "main_thread_block",
        "page": "pictures", "page_path": "/pages/others/pictures/pictures",
        "file": "pages/others/pictures/pictures.js",
        "old": "  onShow: function () {",
        "new": "  onShow: function () {var __t=Date.now();while(Date.now()-__t<1400){}",
        "note": "onShow 同步死循环 1.4s（误写阻塞计算）→ devtools 性能条目/首屏渲染飙升",
    },
]


def coarse_dim(dim: str) -> str:
    return "visual" if dim in ("visual", "layout") else dim
