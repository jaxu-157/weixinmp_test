"""Windows 窗口截图兜底方案。"""
import ctypes
import ctypes.wintypes
import os


def win_screenshot(filepath: str) -> bool:
    """捕获微信开发者工具模拟器区域。"""
    try:
        from PIL import ImageGrab

        user32 = ctypes.windll.user32
        WNDENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
        )
        target_hwnd = None

        def enum_cb(hwnd, lp):
            nonlocal target_hwnd
            if not user32.IsWindowVisible(hwnd):
                return True
            title = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title, 256)
            if "微信开发者工具" in title.value:
                target_hwnd = hwnd
            return True

        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        if not target_hwnd:
            return False

        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(target_hwnd, ctypes.byref(rect))
        x1, y1, x2, y2 = rect.left, rect.top, rect.right, rect.bottom
        w = x2 - x1
        h = y2 - y1
        sim_x1 = x1 + int(w * 0.02)
        sim_y1 = y1 + int(h * 0.08)
        sim_x2 = x1 + int(w * 0.45)
        sim_y2 = y2 - int(h * 0.02)
        img = ImageGrab.grab(bbox=(sim_x1, sim_y1, sim_x2, sim_y2))
        img.save(filepath)
        return True
    except Exception:
        return False
