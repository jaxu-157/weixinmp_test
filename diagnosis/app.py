"""Vision-Triage 诊断服务 & Mock API"""
import time
import random
from typing import Optional
from fastapi import FastAPI, File, UploadFile, Header, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Vision-Triage Diagnosis Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ 故障状态管理 ============

current_fault_profile = "normal"
counter_value = 0


class FaultActivateRequest(BaseModel):
    profile: str


class FaultStatusResponse(BaseModel):
    profile: str


@app.post("/fault/activate")
async def activate_fault(req: FaultActivateRequest):
    global current_fault_profile
    current_fault_profile = req.profile
    return {"code": 0, "data": None, "profile": current_fault_profile}


@app.get("/fault/status")
async def fault_status():
    return {"code": 0, "data": {"profile": current_fault_profile}, "profile": current_fault_profile}


# ============ Mock API：Feed ============

SAMPLE_IMAGES = [
    "https://picsum.photos/400/300?random=1",
    "https://picsum.photos/400/300?random=2",
    "https://picsum.photos/400/300?random=3",
    "https://picsum.photos/400/300?random=4",
    "https://picsum.photos/400/300?random=5",
    "https://picsum.photos/400/300?random=6",
    "https://picsum.photos/400/300?random=7",
    "https://picsum.photos/400/300?random=8",
]

BLUR_IMAGES = [
    "https://picsum.photos/400/300?blur=10&random=1",
    "https://picsum.photos/400/300?blur=10&random=2",
    "https://picsum.photos/400/300?blur=10&random=3",
    "https://picsum.photos/400/300?blur=10&random=4",
]


@app.get("/api/feed")
async def get_feed(
    page: int = 1,
    pageSize: int = 10,
    x_fault_profile: Optional[str] = Header(None, alias="X-Fault-Profile"),
):
    profile = current_fault_profile if current_fault_profile != "normal" else (x_fault_profile or "normal")

    # slow_api故障：延迟返回
    if profile in ("slow_api", "mixed_fault"):
        await _simulate_delay(800, 1500)

    items = []
    for i in range((page - 1) * pageSize, page * pageSize):
        # blur_image故障：返回模糊图片URL
        if profile == "blur_image":
            img = BLUR_IMAGES[i % len(BLUR_IMAGES)]
        else:
            img = SAMPLE_IMAGES[i % len(SAMPLE_IMAGES)]

        items.append({
            "id": i + 1,
            "title": f"图片 {i + 1}",
            "subtitle": f"这是第 {i + 1} 张图片的描述",
            "imageUrl": img,
            "tags": random.sample(["风景", "人物", "建筑", "美食", "动物"], k=2),
        })

    return {"code": 0, "data": items, "profile": profile}


# ============ Mock API：Counter ============

@app.get("/api/counter")
async def get_counter(
    x_fault_profile: Optional[str] = Header(None, alias="X-Fault-Profile"),
):
    profile = current_fault_profile if current_fault_profile != "normal" else (x_fault_profile or "normal")

    if profile in ("slow_api", "mixed_fault"):
        await _simulate_delay(800, 1500)

    return {
        "code": 0,
        "data": {
            "value": counter_value,
            "updatedAt": int(time.time() * 1000),
            "version": f"v{counter_value}",
        },
        "profile": profile,
    }


@app.post("/api/counter/refresh")
async def refresh_counter(
    x_fault_profile: Optional[str] = Header(None, alias="X-Fault-Profile"),
):
    global counter_value
    profile = current_fault_profile if current_fault_profile != "normal" else (x_fault_profile or "normal")

    if profile in ("slow_api", "mixed_fault"):
        await _simulate_delay(800, 1500)

    counter_value += 1

    data = {
        "value": counter_value,
        "updatedAt": int(time.time() * 1000),
        "version": f"v{counter_value}",
    }

    # wrong_mapping故障：字段名不对
    if profile == "wrong_mapping":
        data = {
            "val": counter_value,  # 前端期望 value 字段
            "time": int(time.time() * 1000),
            "ver": f"v{counter_value}",
        }

    return {"code": 0, "data": data, "profile": profile}


# ============ Mock API：Layout ============

@app.get("/api/layout")
async def get_layout(
    x_fault_profile: Optional[str] = Header(None, alias="X-Fault-Profile"),
):
    profile = current_fault_profile if current_fault_profile != "normal" else (x_fault_profile or "normal")

    if profile in ("slow_api", "mixed_fault"):
        await _simulate_delay(800, 1500)

    cards = []
    for i in range(8):
        height = random.choice([200, 250, 300, 350, 400])
        cards.append({
            "id": i + 1,
            "title": f"布局卡片 {i + 1}" + ("—这是一个很长的标题用于测试溢出效果" if i % 3 == 0 else ""),
            "description": f"卡片 {i + 1} 的详细描述，用于验证多行文本的截断显示效果。",
            "imageUrl": SAMPLE_IMAGES[i % len(SAMPLE_IMAGES)],
            "width": 400,
            "height": height,
            "tags": random.sample(["UI", "布局", "压力", "测试", "溢出"], k=2),
        })

    return {"code": 0, "data": cards, "profile": profile}


# ============ 诊断 API ============

@app.post("/diagnose")
async def diagnose(
    screenshot: UploadFile = File(...),
    page_type: str = Form("feed"),
    fault_profile: str = Form("normal"),
    page_state: Optional[str] = Form(None),
    perf_data: Optional[str] = Form(None),
):
    """综合诊断接口：接收截图和上下文，返回分诊结果"""
    import json
    from diagnose.triage import run_triage

    image_bytes = await screenshot.read()

    state = json.loads(page_state) if page_state else {}
    perf = json.loads(perf_data) if perf_data else {}

    result = run_triage(
        image_bytes=image_bytes,
        page_type=page_type,
        fault_profile=fault_profile,
        page_state=state,
        perf_data=perf,
    )

    return {"code": 0, "data": result, "profile": fault_profile}


# ============ 工具函数 ============

async def _simulate_delay(min_ms: int, max_ms: int):
    import asyncio
    delay = random.randint(min_ms, max_ms) / 1000.0
    await asyncio.sleep(delay)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8900, reload=True)
