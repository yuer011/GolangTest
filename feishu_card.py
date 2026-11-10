"""FeishuCardResolver：飞书机器人卡片按钮回调。

⏸️ v0.2 再实装；v0.1 仅占位 stub。
"""
from __future__ import annotations

from typing import Any

from .base import ResumeResult


class FeishuCardResolver:
    name = "feishu_card"

    def wait(self, payload: Any, timeout_sec: int) -> ResumeResult:
        raise NotImplementedError("v0.1 未实现 FeishuCardResolver，预计 v0.2 提供")

    def cancel(self) -> None:
        pass
