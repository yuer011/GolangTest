"""飞书自定义机器人通知。骨架阶段。"""
from __future__ import annotations

from .base import NotifyEvent, NotifyPayload


class FeishuBotNotifier:
    name = "feishu_bot"

    def __init__(self, webhook: str, secret: str | None = None, timeout: float = 5.0):
        self.webhook = webhook
        self.secret = secret
        self.timeout = timeout

    def send(self, event: NotifyEvent, payload: NotifyPayload) -> None:
        raise NotImplementedError("骨架阶段：FeishuBotNotifier.send 待 notify 实装")
