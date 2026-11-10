"""平台探测 + 强制覆盖

骨架阶段：仅提供 Platform 枚举 / detect() / 占位 CURRENT。
实际启动逻辑（读 config.platform.override）由 run.py 在初始化时设置。
"""
from __future__ import annotations

import platform as _plat
from enum import Enum


class Platform(str, Enum):
    MAC = "mac"
    WINDOWS = "windows"


def detect() -> Platform:
    sys = _plat.system().lower()
    if sys == "darwin":
        return Platform.MAC
    if sys == "windows":
        return Platform.WINDOWS
    raise RuntimeError(f"Unsupported platform: {sys}")


# 全局只读单例（骨架阶段直接用 detect()，runner 可用 set_current() 覆盖）
CURRENT: Platform = detect()


def set_current(p: Platform) -> None:
    """允许 config.platform.override 在启动早期覆盖。"""
    global CURRENT
    CURRENT = p
