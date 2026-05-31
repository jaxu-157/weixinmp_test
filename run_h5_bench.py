#!/usr/bin/env python3
"""一键 H5 基准测试（自动启停静态服务器）"""
import subprocess, sys, os, time

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

SCRIPTS = {
    "bench": "fault_bench/bench/run_bench.py",
    "campaign": "fault_bench/bench/run_campaign.py",
    "crosspage": "fault_bench/bench/crosspage_bench.py",
}
if len(sys.argv) < 2 or sys.argv[1] not in SCRIPTS:
    print(f"用法: python run_h5_bench.py <{'|'.join(SCRIPTS)}>")
    sys.exit(1)

server = subprocess.Popen(
    [sys.executable, "-m", "http.server", "8099", "--bind", "127.0.0.1",
     "--directory", "fault_bench/xtx/dist/build/h5"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)

try:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    subprocess.run([sys.executable, SCRIPTS[sys.argv[1]]], env=env).check_returncode()
finally:
    server.terminate()
