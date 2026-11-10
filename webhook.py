"""通用 Webhook 通知（POST JSON）。骨架阶段。"""
from __future__ import annotations

from .base import NotifyEvent, NotifyPayload


class WebhookNotifier:
    name = "webhook"

    def __init__(self, url: str, headers: dict | None = None, timeout: float = 5.0):
        self.url = url
        self.headers = headers or {}
        self.timeout = timeout

    def send(self, event: NotifyEvent, payload: NotifyPayload) -> None:
        raise NotImplementedError("骨架阶段：WebhookNotifier.send 待 notify 实装")
