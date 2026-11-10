"""动作执行器：归一化 action dict -> pyautogui / actions。

action dict 统一格式（由 parser 产出）：
    {"type": "click",        "start": [x, y]}
    {"type": "left_double",  "start": [x, y]}
    {"type": "right_single", "start": [x, y]}
    {"type": "drag",         "start": [x1, y1], "end": [x2, y2]}
    {"type": "hotkey",       "key": "mod+c"}          # mod 由本类翻译
    {"type": "type",         "content": "文本"}
    {"type": "scroll",       "start": [x, y], "direction": "up|down|left|right"}
    {"type": "wait"}
    {"type": "finished"}
    {"type": "call_user"}

坐标为 1000×1000 归一化，落地像素由注入的 Screen.to_px 换算。
"""
from __future__ import annotations

import re
import time
from typing import Any

from dlp_auto.core.platform import Platform

_FINISH_TYPES = {"finished", "call_user"}
_CLICK_TYPES = {"click", "left_double", "right_single"}
_SCROLL_CLICKS = 5
_DRAG_HOLD_AT_START_SEC = 0.4   # 按下后在起点停留，确保拾起
_DRAG_HOLD_AT_END_SEC = 1.0     # 到终点后停留再松开，让目标区域稳定接收 drop
_DRAG_MOVE_DURATION_SEC = 0.8   # 拖拽移动时长（放慢，避免 Electron 漏接拖拽事件）


class Executor:
    def __init__(self, platform: Platform, screen: Any, *,
                 failsafe: bool = True, type_interval: float = 0.02,
                 move_duration: float = 0.2, click_pause: float = 0.05):
        self.platform = platform
        self.screen = screen
        self._mod_key = "command" if platform == Platform.MAC else "ctrl"
        self.type_interval = type_interval
        self.move_duration = move_duration
        self.click_pause = click_pause

        import pyautogui
        pyautogui.FAILSAFE = failsafe
        pyautogui.PAUSE = click_pause

    # ── 平台动作模块（懒加载，避免 import 期触发 GUI 依赖） ──────────
    @property
    def _actions(self):
        from dlp_auto import actions
        return actions

    # ── 主入口 ──────────────────────────────────────────────────────
    def do(self, action: dict[str, Any]) -> tuple[bool, str]:
        """执行单个 action，返回 (is_finished, observation)。"""
        import pyautogui

        atype = action.get("type", "unknown")

        if atype in _FINISH_TYPES:
            return True, atype

        if atype == "wait":
            time.sleep(5.0)
            return False, "waited 5s"

        if atype in _CLICK_TYPES:
            x, y = self.screen.to_px(action["start"])
            if atype == "click":
                pyautogui.click(x, y)
            elif atype == "left_double":
                pyautogui.doubleClick(x, y)
            else:
                pyautogui.rightClick(x, y)
            return False, f"{atype} at ({x},{y})"

        if atype == "drag":
            sx, sy = self.screen.to_px(action["start"])
            ex, ey = self.screen.to_px(action["end"])
            if self.platform == Platform.MAC:
                self._drag_mac(sx, sy, ex, ey)
            else:
                self._drag_win(sx, sy, ex, ey)
            return False, f"drag ({sx},{sy})->({ex},{ey})"

        if atype == "hotkey":
            keys = self._translate_keys(action["key"])
            self._actions.keyboard.hotkey(*keys)
            return False, f"hotkey {'+'.join(keys)}"

        if atype == "type":
            content = action.get("content", "")
            self._actions.keyboard.type_text(content, interval=self.type_interval)
            return False, f"typed: {content[:30]!r}"

        if atype == "scroll":
            x, y = self.screen.to_px(action["start"])
            direction = (action.get("direction") or "down").lower()
            pyautogui.moveTo(x, y)
            self._scroll(direction)
            return False, f"scroll {direction} at ({x},{y})"

        return False, f"unknown_skipped: {atype!r}"

    # ── 内部工具 ────────────────────────────────────────────────────
    def _translate_keys(self, key: str) -> list[str]:
        """拆分组合键并把抽象 'mod' 翻译为平台修饰键。"""
        out = []
        for k in re.split(r"[+\s]+", key.strip()):
            if not k:
                continue
            kl = k.lower()
            if kl in ("mod", "cmd", "command", "ctrl", "control"):
                out.append(self._mod_key if kl == "mod" else self._norm_mod(kl))
            else:
                out.append(kl)
        return out

    @staticmethod
    def _norm_mod(k: str) -> str:
        if k in ("cmd", "command"):
            return "command"
        return "ctrl"

    @staticmethod
    def _drag_mac(sx: int, sy: int, ex: int, ey: int) -> None:
        """用 Quartz CGEvent 合成原生拖拽：down → 连续 dragged → up。

        pyautogui 的 mouseDown/moveTo/mouseUp 在飞书等 Electron 应用上拖放
        失效（与回车不被接收同源）：它发出的拖动事件序列不完整，缺少中途
        持续的 LeftMouseDragged 事件，Electron 收不到完整的拖放会话。
        改用 Quartz CGEvent（Accessibility 权限，已授权）合成规范拖拽序列：
          1) LeftMouseDown 于起点；
          2) 沿途多次 LeftMouseDragged（分步插值，模拟真实拖动）；
          3) 终点停留后 LeftMouseUp。
        起点/终点各停留一段，避免应用漏接首尾事件。
        """
        import Quartz

        steps = 40
        left = Quartz.kCGMouseButtonLeft

        def post(etype, x, y):
            ev = Quartz.CGEventCreateMouseEvent(None, etype, (x, y), left)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)

        post(Quartz.kCGEventMouseMoved, sx, sy)
        time.sleep(0.1)
        post(Quartz.kCGEventLeftMouseDown, sx, sy)
        time.sleep(_DRAG_HOLD_AT_START_SEC)

        for i in range(1, steps + 1):
            t = i / steps
            x = sx + (ex - sx) * t
            y = sy + (ey - sy) * t
            post(Quartz.kCGEventLeftMouseDragged, x, y)
            time.sleep(_DRAG_MOVE_DURATION_SEC / steps)

        time.sleep(_DRAG_HOLD_AT_END_SEC)
        post(Quartz.kCGEventLeftMouseUp, ex, ey)

    @staticmethod
    def _drag_win(sx: int, sy: int, ex: int, ey: int) -> None:
        """Windows 原生拖拽：moveTo 起点 → mouseDown → 分步 moveTo → mouseUp。

        与 mac 端同理放慢并分步移动，确保 Electron（飞书）收到完整的
        鼠标拖动序列；首尾各停留一段，避免应用漏接 down/up。
        """
        import pyautogui

        steps = 40
        pyautogui.moveTo(sx, sy)
        time.sleep(0.1)
        pyautogui.mouseDown(sx, sy, button="left")
        time.sleep(_DRAG_HOLD_AT_START_SEC)

        for i in range(1, steps + 1):
            t = i / steps
            x = int(sx + (ex - sx) * t)
            y = int(sy + (ey - sy) * t)
            pyautogui.moveTo(x, y)
            time.sleep(_DRAG_MOVE_DURATION_SEC / steps)

        time.sleep(_DRAG_HOLD_AT_END_SEC)
        pyautogui.mouseUp(ex, ey, button="left")

    @staticmethod
    def _scroll(direction: str) -> None:
        import pyautogui

        mapping = {"up": _SCROLL_CLICKS, "down": -_SCROLL_CLICKS,
                   "left": -_SCROLL_CLICKS, "right": _SCROLL_CLICKS}
        delta = mapping.get(direction, -_SCROLL_CLICKS)
        if direction in ("left", "right"):
            pyautogui.hscroll(delta)
        else:
            pyautogui.scroll(delta)
