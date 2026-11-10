"""截图 / 坐标换算 / 落盘策略。

- capture(persist, name) -> Screenshot(b64, path, size)
- to_px(norm_xy)：1000×1000 归一化坐标 → 实际逻辑像素
- resize_to：目标高度（int），喂模型前按宽高比缩放（D10）

依赖（pyautogui / Pillow）懒加载，使纯配置场景下 import 本模块不强依赖 GUI。
"""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class Screenshot:
    b64: str
    path: Optional[Path] = None
    size: Optional[tuple[int, int]] = None  # resize 后的 (w, h)


# 归一化坐标落地像素时离屏幕四边保留的安全边距（px）。避免贴角坐标（如 [0,0]）踩中
# pyautogui 的 fail-safe（鼠标到屏幕四角会抛 FailSafeException）。取 2px：肉眼/交互上
# 与真正的边缘无差别（截图框选、拖拽落点都不受影响），却足以绕开角点判定。
_EDGE_MARGIN_PX = 2


class Screen:
    def __init__(self, resize_to: int | None = 1080,
                 out_dir: Optional[Path] = None):
        self.resize_to = resize_to
        self.out_dir = Path(out_dir) if out_dir else None

    def capture(self, persist: bool = False, name: str | None = None) -> Screenshot:
        import pyautogui

        img = pyautogui.screenshot()
        if self.resize_to:
            img = self._resize_by_height(img, self.resize_to)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        raw = buf.getvalue()
        b64 = base64.b64encode(raw).decode("utf-8")

        path: Optional[Path] = None
        if persist:
            path = self._persist(raw, name)

        return Screenshot(b64=b64, path=path, size=img.size)

    def to_px(self, xy: tuple[int, int]) -> tuple[int, int]:
        import pyautogui

        w, h = pyautogui.size()
        # 夹到屏幕内、且**离四边留出安全边距**：pyautogui 的 fail-safe 会在鼠标移到屏幕
        # **四个角**（如 (0,0)）时抛 FailSafeException。而「框选尽量大」的截图类 case，模型
        # 常给出 [0,0]→[1000,1000] 这种贴角坐标，换算成 (0,0) 正好踩中 fail-safe → case 崩成
        # error（实测 WeLink 自带截图）。这里把落点收进离边 _EDGE_MARGIN_PX 的范围：既保留
        # fail-safe 兜底真正失控的情况，又让「合法的近全屏框选」不再误触发。
        x = max(_EDGE_MARGIN_PX, min(w - 1 - _EDGE_MARGIN_PX, round(w * xy[0] / 1000)))
        y = max(_EDGE_MARGIN_PX, min(h - 1 - _EDGE_MARGIN_PX, round(h * xy[1] / 1000)))
        return (x, y)

    @staticmethod
    def _resize_by_height(img, target_h: int):
        w, h = img.size
        if h <= target_h:
            return img
        target_w = round(w * target_h / h)
        return img.resize((target_w, target_h))

    def _persist(self, raw: bytes, name: str | None) -> Path:
        out_dir = self.out_dir or Path("screenshots")
        out_dir.mkdir(parents=True, exist_ok=True)
        if not name:
            name = datetime.now().strftime("shot_%Y%m%d_%H%M%S_%f")
        if not name.endswith(".png"):
            name += ".png"
        path = out_dir / name
        path.write_bytes(raw)
        return path
