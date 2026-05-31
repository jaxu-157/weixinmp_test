"""Threshold sweep for the tiled-SSIM visual channel.

Reads a saved bench_report JSON and, WITHOUT re-rendering, sweeps the tile-SSIM
regression threshold to show the detection-recall vs healthy-false-positive
tradeoff. This is the honest way to present the tiled channel's headroom instead
of cherry-picking one threshold: the operating point should be chosen by the
healthy-control floor, not by maximizing recall on faults.
"""
from __future__ import annotations
import glob, json, os, sys

OUT = os.path.join(os.path.dirname(__file__), "..", "bench_out")


def latest():
    fs = sorted(glob.glob(os.path.join(OUT, "bench_report_*.json")))
    return fs[-1] if fs else None


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else latest()
    d = json.load(open(path, encoding="utf-8"))
    faults = [c for c in d["cases"] if c["kind"] == "fault" and "error" not in c]
    healthy = [c for c in d["cases"] if c["kind"] == "healthy"]
    nf, nh = len(faults), len(healthy)

    def tmin(c):
        v = c.get("raw_channels", {}).get("tiled_min_ssim")
        return 1.0 if v is None else v

    def other_detect(c):
        # non-tiled channels (whole SSIM, webug, verdict, crash) — tiling is additive on top
        rc = c.get("raw_channels", {})
        return (c["verdict"] not in ("Pass", "Unknown") or rc.get("baseline_regression")
                or rc.get("webug_r2") or rc.get("webug_r3") or c["channels"].get("crash"))

    print(f"report: {os.path.basename(path)}  faults={nf} healthy={nh}")
    print(f"healthy tile floor (min over controls) = {min((tmin(c) for c in healthy), default=1.0)}")
    print(f"\n{'thr':>5} | tiled-only R | +multichannel R | healthy FP")
    print("-" * 52)
    for thr in (0.80, 0.85, 0.90, 0.92, 0.95, 0.98, 0.99):
        tiled_rec = sum(1 for c in faults if tmin(c) < thr) / nf
        multi_rec = sum(1 for c in faults if (tmin(c) < thr or other_detect(c))) / nf
        fp = sum(1 for c in healthy if tmin(c) < thr) / nh if nh else 0
        print(f"{thr:5.2f} | {tiled_rec:11.0%}  | {multi_rec:13.0%}   | {fp:8.0%}")

    print("\nper-fault tiled_min_ssim (sorted):")
    for c in sorted(faults, key=tmin):
        print(f"  {tmin(c):.3f}  {c['id']:22s} gt={c['gt_dim']}")


if __name__ == "__main__":
    main()
