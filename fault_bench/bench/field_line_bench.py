"""功能/数据故障的字段级【行号】定位基准(确定性,无 LLM,无需渲染)。

链路最后一公里:已知坏字段名(运行时由数据层给出——minium page.data 直接命名坏字段;
或 ajv/zod 从 API 契约;或 DOM 空节点 diff)→ build_field_line_index → .vue 源码行。

本基准衡量"字段→行"索引的正确性:对每个 bindempty 功能故障,
取其(文件, 坏字段名),用 resolve_field_line 预测行号,与该绑定在源码里的真实行号比对。
真实行号 = 该变异 old 串(形如 '{{ item.name }}')在文件中的行(生成时已保证 count==1)。
"""
from __future__ import annotations
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FB = os.path.abspath(os.path.join(HERE, ".."))
for p in (os.path.dirname(FB), FB, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from bench.gen_random_mutations import generate  # noqa
from bench.localize import build_field_line_index, resolve_field_line  # noqa

SRC = os.path.join(FB, "xtx", "src")
OUT = os.path.join(FB, "campaign_out", "localize_out")


def true_line(file_rel: str, old: str) -> int | None:
    lines = open(os.path.join(SRC, file_rel), encoding="utf-8").read().splitlines()
    for i, l in enumerate(lines):
        if old in l:
            return i + 1
    return None


def field_of(mut_id: str) -> str:
    # id 形如 bindempty@XtxGuess:item.name → item.name
    return mut_id.split(":", 1)[1] if ":" in mut_id else ""


def main():
    os.makedirs(OUT, exist_ok=True)
    fidx = build_field_line_index(SRC)
    funcs = [m for m in generate(SRC, seed=42, pages=["index"]) if m["dim"] == "functional"]
    rows = []
    for m in funcs:
        field = field_of(m["id"])
        gt_line = true_line(m["file"], m["old"])
        pred = resolve_field_line(fidx, m["file"], field)
        pred_lines = pred.get("lines", [])
        hit = bool(gt_line and gt_line in pred_lines)
        rows.append({"id": m["id"], "file": m["file"], "field": field,
                     "gt_line": gt_line, "pred_lines": pred_lines,
                     "via": pred.get("via"), "line_hit": hit})
    n = len(rows)
    n_hit = sum(1 for r in rows if r["line_hit"])
    summary = {"_sentinel": "FIELDLINE_OK", "n_functional": n,
               "field_line_exact": f"{n_hit}/{n}=" + (f"{n_hit/n:.3f}" if n else "NA")}
    json.dump({"summary": summary, "rows": rows},
              open(os.path.join(OUT, "field_line.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False))
    print("[done]", os.path.join(OUT, "field_line.json"))


if __name__ == "__main__":
    main()
