"""API 端点集成测试集

测试目标：验证 FastAPI 各端点在不同 fault profile 下的正确行为
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import time
import asyncio
from fastapi.testclient import TestClient
from app import app


client = TestClient(app)


class TestFaultManagement:
    """故障管理 API 测试"""

    def test_default_profile_is_normal(self):
        """默认 profile 应为 normal"""
        resp = client.get("/fault/status")
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["profile"] == "normal"
        return data

    def test_activate_slow_api(self):
        """激活 slow_api 应正确切换"""
        resp = client.post("/fault/activate", json={"profile": "slow_api"})
        data = resp.json()
        assert data["code"] == 0
        assert data["profile"] == "slow_api"
        # 验证状态
        status = client.get("/fault/status").json()
        assert status["data"]["profile"] == "slow_api"
        # 恢复
        client.post("/fault/activate", json={"profile": "normal"})
        return data

    def test_activate_all_profiles(self):
        """所有 profile 都应能激活"""
        profiles = ["normal", "slow_api", "blur_image", "stale_ui",
                    "wrong_mapping", "layout_overlap", "memory_pressure", "mixed_fault"]
        results = []
        for p in profiles:
            resp = client.post("/fault/activate", json={"profile": p})
            assert resp.json()["code"] == 0, f"激活 {p} 失败"
            results.append(p)
        client.post("/fault/activate", json={"profile": "normal"})
        return {"activated": results}


class TestFeedAPI:
    """Feed API 测试"""

    def test_normal_feed(self):
        """正常模式应返回正确数据"""
        client.post("/fault/activate", json={"profile": "normal"})
        resp = client.get("/api/feed?page=1&pageSize=5")
        data = resp.json()
        assert data["code"] == 0
        assert len(data["data"]) == 5
        assert data["data"][0]["id"] == 1
        assert "title" in data["data"][0]
        assert "imageUrl" in data["data"][0]
        return data

    def test_blur_image_urls(self):
        """blur_image 模式应返回模糊图片URL"""
        client.post("/fault/activate", json={"profile": "blur_image"})
        resp = client.get("/api/feed?page=1&pageSize=3")
        data = resp.json()
        for item in data["data"]:
            assert "blur" in item["imageUrl"], f"blur模式图片URL无blur参数: {item['imageUrl']}"
        client.post("/fault/activate", json={"profile": "normal"})
        return data

    def test_feed_pagination(self):
        """分页应正确工作"""
        resp1 = client.get("/api/feed?page=1&pageSize=3")
        resp2 = client.get("/api/feed?page=2&pageSize=3")
        data1 = resp1.json()["data"]
        data2 = resp2.json()["data"]
        assert data1[0]["id"] == 1
        assert data2[0]["id"] == 4
        return {"page1_first_id": data1[0]["id"], "page2_first_id": data2[0]["id"]}

    def test_feed_header_profile_override(self):
        """通过 Header 传递 profile 应覆盖全局设置"""
        client.post("/fault/activate", json={"profile": "normal"})
        resp = client.get("/api/feed?page=1&pageSize=2",
                         headers={"X-Fault-Profile": "blur_image"})
        data = resp.json()
        assert data["profile"] == "blur_image"
        assert "blur" in data["data"][0]["imageUrl"]
        return data

    def test_slow_api_latency(self):
        """slow_api 模式应有明显延迟"""
        client.post("/fault/activate", json={"profile": "slow_api"})
        start = time.time()
        resp = client.get("/api/feed?page=1&pageSize=2")
        elapsed = time.time() - start
        assert elapsed > 0.7, f"slow_api延迟不足: {elapsed:.2f}s"
        client.post("/fault/activate", json={"profile": "normal"})
        return {"elapsed_s": round(elapsed, 3)}


class TestCounterAPI:
    """Counter API 测试"""

    def test_counter_get(self):
        """获取计数器应返回当前值"""
        resp = client.get("/api/counter")
        data = resp.json()
        assert data["code"] == 0
        assert "value" in data["data"]
        assert "updatedAt" in data["data"]
        assert "version" in data["data"]
        return data

    def test_counter_refresh_increments(self):
        """刷新应递增计数器"""
        client.post("/fault/activate", json={"profile": "normal"})
        resp1 = client.get("/api/counter").json()
        val_before = resp1["data"]["value"]
        client.post("/api/counter/refresh")
        resp2 = client.get("/api/counter").json()
        val_after = resp2["data"]["value"]
        assert val_after == val_before + 1, f"刷新后值未递增: {val_before} -> {val_after}"
        return {"before": val_before, "after": val_after}

    def test_wrong_mapping_fields(self):
        """wrong_mapping 模式应返回错误字段名"""
        client.post("/fault/activate", json={"profile": "wrong_mapping"})
        resp = client.post("/api/counter/refresh")
        data = resp.json()["data"]
        assert "val" in data, f"wrong_mapping未返回错误字段: {data.keys()}"
        assert "value" not in data, f"wrong_mapping不应有正确字段: {data.keys()}"
        client.post("/fault/activate", json={"profile": "normal"})
        return data

    def test_slow_api_counter_latency(self):
        """slow_api 模式计数器应有延迟"""
        client.post("/fault/activate", json={"profile": "slow_api"})
        start = time.time()
        client.post("/api/counter/refresh")
        elapsed = time.time() - start
        assert elapsed > 0.7, f"slow_api延迟不足: {elapsed:.2f}s"
        client.post("/fault/activate", json={"profile": "normal"})
        return {"elapsed_s": round(elapsed, 3)}


class TestLayoutAPI:
    """Layout API 测试"""

    def test_layout_returns_cards(self):
        """应返回布局卡片列表"""
        resp = client.get("/api/layout")
        data = resp.json()
        assert data["code"] == 0
        assert len(data["data"]) == 8
        card = data["data"][0]
        assert "title" in card
        assert "width" in card
        assert "height" in card
        assert "tags" in card
        return data

    def test_layout_card_dimensions(self):
        """卡片尺寸应在合理范围"""
        resp = client.get("/api/layout")
        for card in resp.json()["data"]:
            assert card["width"] == 400
            assert 200 <= card["height"] <= 400
        return {"validated": True}


class TestDiagnoseAPI:
    """诊断 API 测试"""

    def _make_test_image(self):
        """生成测试图像：含清晰纹理和文字，确保不被误判为模糊"""
        import cv2
        import numpy as np
        img = np.zeros((200, 200, 3), dtype=np.uint8)
        # 棋盘格纹理确保高频（不模糊）
        for i in range(0, 200, 20):
            for j in range(0, 200, 20):
                if (i // 20 + j // 20) % 2 == 0:
                    img[i:i+20, j:j+20] = [180, 180, 180]
                else:
                    img[i:i+20, j:j+20] = [60, 60, 60]
        cv2.putText(img, "TEST", (30, 120), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 0), 3)
        _, buf = cv2.imencode(".png", img)
        return buf.tobytes()

    def test_diagnose_normal(self):
        """正常图像+正常状态应返回 Pass"""
        import io
        img_bytes = self._make_test_image()
        resp = client.post(
            "/diagnose",
            files={"screenshot": ("test.png", io.BytesIO(img_bytes), "image/png")},
            data={
                "page_type": "counter",
                "fault_profile": "normal",
                "page_state": json.dumps({"visibleValue": 5, "expectedValue": 5}),
                "perf_data": json.dumps({"interactionMs": 100, "memoryWarningCount": 0}),
            },
        )
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["verdict"] == "Pass"
        return data

    def test_diagnose_performance_risk(self):
        """正常图像+高延迟应返回 PerformanceRisk"""
        import io
        img_bytes = self._make_test_image()
        resp = client.post(
            "/diagnose",
            files={"screenshot": ("test.png", io.BytesIO(img_bytes), "image/png")},
            data={
                "page_type": "counter",
                "fault_profile": "slow_api",
                "page_state": json.dumps({"visibleValue": 5, "expectedValue": 5}),
                "perf_data": json.dumps({"interactionMs": 1500, "memoryWarningCount": 0}),
            },
        )
        data = resp.json()
        assert data["data"]["verdict"] == "PerformanceRisk"
        return data

    def test_diagnose_functional_fail(self):
        """正常图像+数据不一致应返回 FunctionalFail"""
        import io
        img_bytes = self._make_test_image()
        resp = client.post(
            "/diagnose",
            files={"screenshot": ("test.png", io.BytesIO(img_bytes), "image/png")},
            data={
                "page_type": "counter",
                "fault_profile": "stale_ui",
                "page_state": json.dumps({"visibleValue": 1, "expectedValue": 5}),
                "perf_data": json.dumps({"interactionMs": 200, "memoryWarningCount": 0}),
            },
        )
        data = resp.json()
        assert data["data"]["verdict"] == "FunctionalFail"
        return data


def run_api_tests():
    """运行所有 API 测试"""
    suites = [
        ("故障管理", TestFaultManagement()),
        ("Feed API", TestFeedAPI()),
        ("Counter API", TestCounterAPI()),
        ("Layout API", TestLayoutAPI()),
        ("诊断 API", TestDiagnoseAPI()),
    ]

    total_passed = 0
    total_failed = 0
    all_results = []

    for suite_name, suite in suites:
        print(f"\n  [{suite_name}]")
        methods = [m for m in dir(suite) if m.startswith("test_")]
        for method_name in sorted(methods):
            test_fn = getattr(suite, method_name)
            display_name = method_name.replace("test_", "").replace("_", " ")
            try:
                result = test_fn()
                total_passed += 1
                all_results.append({"name": f"{suite_name}/{display_name}", "status": "PASS"})
                print(f"    ✓ {display_name}")
            except AssertionError as e:
                total_failed += 1
                all_results.append({"name": f"{suite_name}/{display_name}", "status": "FAIL", "error": str(e)})
                print(f"    ✗ {display_name}: {e}")
            except Exception as e:
                total_failed += 1
                all_results.append({"name": f"{suite_name}/{display_name}", "status": "ERROR", "error": str(e)})
                print(f"    ! {display_name}: {e}")

    total = total_passed + total_failed
    return {"passed": total_passed, "failed": total_failed, "total": total, "results": all_results}


if __name__ == "__main__":
    print("=" * 60)
    print("API 端点集成测试集")
    print("=" * 60)
    summary = run_api_tests()
    print(f"\n结果: {summary['passed']}/{summary['total']} 通过, {summary['failed']} 失败")
