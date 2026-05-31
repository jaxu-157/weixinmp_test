"""真机正向闭环证明(可逆 setData 注入):
  1. 连 devtools(connect, 只读不关) → 读真实 page.data
  2. 记录某字段原值 → setData 把它置成坏值(undefined/空) → 读回 page.data
  3. 字段扫描器 collect_data 抓坏字段路径(真机真实数据)
  4. setData 恢复原值 → 再读确认恢复
零侵入原则:只临时改运行态数据,测后恢复;绝不 shutdown(不关用户 devtools)。
"""
from __future__ import annotations
import json, os, sys, copy

PORT = int(os.environ.get("MINIUM_PORT", "33676"))
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
for p in (HERE, REPO):
    if p not in sys.path:
        sys.path.insert(0, p)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from devtools_probe import DevtoolsProbe  # noqa: E402
OUT = os.path.join(REPO, "fault_bench", "campaign_out", "localize_out", "datafield_live_inject.json")


def main():
    import minium
    res = {"port": PORT}
    mini = minium.Minium({"connect_to_existing": True, "test_port": PORT, "platform": "ide",
                          "auto_relaunch": False})
    probe = DevtoolsProbe(mini)
    page = mini.app.get_current_page()
    res["route"] = getattr(page, "path", None) or str(page)

    data = page.data
    res["data_keys"] = list(data.keys()) if isinstance(data, dict) else None
    # 选注入目标:list[0] 的第一个字符串字段
    target_key, target_idx, target_field, orig_val = None, None, None, None
    lst = data.get("list") if isinstance(data, dict) else None
    if isinstance(lst, list) and lst and isinstance(lst[0], dict):
        target_key = "list"; target_idx = 0
        for k, v in lst[0].items():
            if isinstance(v, str) and v:
                target_field = k; orig_val = v; break
    res["inject_target"] = {"key": target_key, "idx": target_idx, "field": target_field,
                            "orig_value": orig_val}
    if not target_field:
        res["error"] = "no string field in list[0] to inject"
        json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
        print(json.dumps(res, ensure_ascii=False, indent=2)); return

    # --- 注入坏值(可逆):list[0].<field> = "undefined" 。minium 用 call_method 调页面 setData ---
    new_list = copy.deepcopy(lst)
    new_list[target_idx][target_field] = "undefined"
    page.call_method("setData", {"list": new_list})
    import time; time.sleep(0.6)

    after = probe.collect_data()   # 真机读回 + 字段扫描
    res["after_inject"] = {"broken_field_paths": after.get("broken_field_paths"),
                           "suspicious_fields": after.get("suspicious_fields"),
                           "has_suspicious": after.get("has_suspicious")}
    expect_path = f"{target_key}[{target_idx}].{target_field}"
    res["expected_path"] = expect_path
    res["caught_on_device"] = expect_path in (after.get("broken_field_paths") or [])

    # --- 恢复 ---
    restore = copy.deepcopy(new_list)
    restore[target_idx][target_field] = orig_val
    page.call_method("setData", {"list": restore})
    time.sleep(0.4)
    back = probe.collect_data()
    res["after_restore_broken_paths"] = back.get("broken_field_paths")
    res["restored_clean"] = not (expect_path in (back.get("broken_field_paths") or []))

    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
    print(json.dumps({k: res[k] for k in
          ("route", "inject_target", "after_inject", "expected_path",
           "caught_on_device", "restored_clean")}, ensure_ascii=False, indent=2))
    print("[live-inject] done, devtools left open. →", OUT)


if __name__ == "__main__":
    main()
