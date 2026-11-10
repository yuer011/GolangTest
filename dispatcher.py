"""多通道分发 + 事件过滤。失败不阻塞主流程。"""
from __future__ import annotations

import logging
from typing import Iterable

from .base import Notifier, NotifyEvent, NotifyPayload

log = logging.getLogger("dlp_auto.notify")


class NotifyDispatcher:
    def __init__(self, channels: Iterable[Notifier], events: Iterable[NotifyEvent]):
        self.channels = list(channels)
        self.events = set(events)

    def emit(self, event: NotifyEvent, payload: NotifyPayload) -> None:
        if event not in self.events:
            return
        for ch in self.channels:
            try:
                ch.send(event, payload)
            except Exception as e:  # 通知失败不能影响主流程（D12）
                log.warning("notify channel %s failed: %s", ch.name, e)
