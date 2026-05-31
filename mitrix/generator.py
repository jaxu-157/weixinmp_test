"""组合测试用例生成器。

生成策略：
  - 6 个原子故障：blur_image, slow_api, stale_ui, wrong_mapping, layout_overlap, memory_pressure
  - 每个原子故障有页面适用性约束
  - 单故障：全部6个
  - 两两组合：只在共享页面上测试（C(6,2)=15 中有部分不可测）
  - 三故障组合：选有代表性的
  - 输出 JSON 供 runner 消费
"""
import json
import os
from itertools import combinations

# ============================================================
# 原子故障定义
# ============================================================
ATOMIC_FAULTS = [
    "blur_image",
    "slow_api",
    "stale_ui",
    "wrong_mapping",
    "layout_overlap",
    "memory_pressure",
]

# 每个原子故障可以在哪些页面上被检测到
FAULT_PAGES: dict[str, set[str]] = {
    "blur_image":      {"feed"},
    "slow_api":        {"feed", "counter", "layout"},
    "stale_ui":        {"counter"},
    "wrong_mapping":   {"counter"},
    "layout_overlap":  {"layout"},
    "memory_pressure": {"feed", "layout"},
}

# 所有可用页面
ALL_PAGES = ["feed", "counter", "layout"]


def _best_page(faults: list[str]) -> str:
    """为给定故障集合选出最佳测试页面。

    规则：
      页面必须覆盖所有故障（每个故障至少在该页面可检测）；
      平局时优先 feed > counter > layout。
    """
    candidates = []
    for p in ALL_PAGES:
        p_set = FAULT_PAGE_SETS.get(p, set())
        if all(f in p_set for f in faults):
            candidates.append(p)

    if not candidates:
        return None

    # 平局：按页面优先级 feed > counter > layout
    page_order = {"feed": 0, "counter": 1, "layout": 2}
    candidates.sort(key=lambda p: page_order[p])
    return candidates[0]


# 预计算每个页面能检测的所有故障
FAULT_PAGE_SETS: dict[str, set[str]] = {
    p: {f for f in ATOMIC_FAULTS if p in FAULT_PAGES[f]}
    for p in ALL_PAGES
}


def _applicable_faults(page: str) -> list[str]:
    """返回某页面可检测的原子故障列表。"""
    return [f for f in ATOMIC_FAULTS if page in FAULT_PAGES[f]]


def generate_test_cases(
    include_singles: bool = True,
    include_pairs: bool = True,
    include_triples: bool = True,
    max_triples: int = 10,
) -> list[dict]:
    """生成组合测试用例。

    Returns:
        [
            {
                "id": "single/blur_image@feed",
                "faults": ["blur_image"],
                "page": "feed",
                "oracle": {"blur_image": True, "slow_api": False, ...},
            },
            ...
        ]
    """
    cases: list[dict] = []

    # ---- 单故障 ----
    if include_singles:
        for f in ATOMIC_FAULTS:
            page = _best_page([f])
            if page:
                cases.append(_make_case([f], page, f"single/{f}"))

    # ---- 两两组合 ----
    if include_pairs:
        for f1, f2 in combinations(ATOMIC_FAULTS, 2):
            page = _best_page([f1, f2])
            if page:
                cases.append(_make_case([f1, f2], page, f"pair/{f1}+{f2}"))

    # ---- 三故障组合 ----
    if include_triples:
        triples = list(combinations(ATOMIC_FAULTS, 3))
        # 按适用页面数排序，优先选覆盖更广的组合
        triples.sort(key=lambda fs: -max(
            (len(set(FAULT_PAGES.get(f, set())) & set(FAULT_PAGES.get(f2, set())) & set(FAULT_PAGES.get(f3, set())))
             for f, f2, f3 in [fs]), default=0
        ))
        # 实际上是：按共享页面数
        def _shared_score(fs):
            sets = [FAULT_PAGES.get(f, set()) for f in fs]
            return len(sets[0] & sets[1] & sets[2]) if all(sets) else 0
        triples.sort(key=_shared_score, reverse=True)

        count = 0
        seen_pages = set()
        for fs in triples:
            if count >= max_triples:
                break
            page = _best_page(list(fs))
            if not page:
                continue
            key = (page, tuple(sorted(fs)))
            if key in seen_pages:
                continue
            seen_pages.add(key)
            cases.append(_make_case(list(fs), page, f"triple/{'+'.join(fs)}"))
            count += 1

    return cases


def _make_case(faults: list[str], page: str, case_id: str) -> dict:
    """构建单个测试用例，含 oracle 向量。"""
    oracle = {f: (f in faults) for f in ATOMIC_FAULTS}
    return {
        "id": f"{case_id}@{page}",
        "faults": sorted(faults),
        "page": page,
        "oracle": oracle,
    }


def save_test_cases(cases: list[dict], filepath: str):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2, ensure_ascii=False)


def load_test_cases(filepath: str) -> list[dict]:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def print_summary(cases: list[dict]):
    """打印测试用例摘要。"""
    n_single = sum(1 for c in cases if c["id"].startswith("single"))
    n_pair = sum(1 for c in cases if c["id"].startswith("pair"))
    n_triple = sum(1 for c in cases if c["id"].startswith("triple"))

    print(f"测试用例摘要: 总计 {len(cases)} 个")
    print(f"  单故障: {n_single}")
    print(f"  两两组合: {n_pair}")
    print(f"  三故障组合: {n_triple}")
    print()

    for c in cases:
        faults_str = "+".join(c["faults"])
        print(f"  [{c['page']:7s}] {faults_str:<45s}  →  {c['id']}")


if __name__ == "__main__":
    cases = generate_test_cases()
    out = os.path.join(os.path.dirname(__file__), "..", "mitrix_test_cases.json")
    save_test_cases(cases, out)
    print_summary(cases)
    print(f"\n已写入 {out}")
