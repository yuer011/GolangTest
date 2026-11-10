"""WebhookResolver：本地 HTTP server 监听 POST /resume/<token>。骨架阶段。

仅在 config.human.webhook_server.enabled=true 时由 runner 拉起，
否则本类不会被实例化（D14）。
"""
from __future__ import annotations

from typing import Any

from .base import ResumeResult


class WebhookResolver:
    name = "webhook"

    def __init__(self, host: str = "0.0.0.0", port: int = 7421,
                 base_url: str = "http://localhost:7421"):
        self.host = host
        self.port = port
        self.base_url = base_url

    def start(self) -> None:
        raise NotImplementedError("骨架阶段：WebhookResolver.start 待 human 实装")

    def stop(self) -> None:
        raise NotImplementedError("骨架阶段：WebhookResolver.stop 待 human 实装")

    def wait(self, payload: Any, timeout_sec: int) -> ResumeResult:
        raise NotImplementedError("骨架阶段：WebhookResolver.wait 待 human 实装")

    def cancel(self) -> None:
        pass
