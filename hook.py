"""Report Hook 接口：JSON 写完后回调，可用于发飞书 / 转 HTML / 上报 CI 等。"""
from __future__ import annotations

from typing import Protocol

from .schema import RunReport


class ReportHook(Protocol):
    name: str

    def on_report(self, report: RunReport) -> None: ...
