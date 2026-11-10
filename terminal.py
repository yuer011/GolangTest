"""TerminalResolver：终端按 Enter / r / q 决定 resume。骨架阶段。"""
from __future__ import annotations

from typing import Any

from .base import ResumeResult


class TerminalResolver:
    name = "terminal"

    def wait(self, payload: Any, timeout_sec: int) -> ResumeResult:
        raise NotImplementedError("骨架阶段：TerminalResolver.wait 待 human 实装")

    def cancel(self) -> None:
        # 终端等待无法精细 cancel，留给 composite 内部用 thread + Event 处理
        pass
