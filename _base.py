"""dlp_log 后端的平台无关抽象：协议、事件数据结构、纯解析 helper。

这里只放**不含任何平台假设**的东西：
- LogVerifyBackend：一路日志验证后端要实现的接口（on_case_start / check）。
- DlpEvent：从一条真实外发事件日志行解析出的结构化字段。
- 行首时间戳解析、事件行解析等纯函数。

具体某平台「日志在哪、怎么解密、事件行长什么样」全部在 _windows.py / _mac.py 里，
互不引用；本文件被两端共用。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Protocol

from ..outcome import CheckContext, CheckOutcome

# 行首时间戳：[2026-08-03 19:55:02.251]，毫秒可有可无。
_TS_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:\.(\d{1,6}))?\]")


@dataclass
class DlpEvent:
    """从一条真实 DLP 外发事件日志行解析出的字段。"""
    raw_line: str                       # 整条原始日志行（去尾部换行）
    ts: Optional[datetime] = None       # 行首时间戳（本地时钟，无则 None）
    event_uuid: str = ""                # 事件UUID
    process_name: str = ""              # process name is <exe>
    origin_file_path: str = ""          # origin file path is <路径 / screenshot.png>
    tag_name: str = ""                  # tag name is <...>
    extras: dict[str, Any] = field(default_factory=dict)


class EventCollectError(Exception):
    """collect_events 无法完成时抛出（配置缺失 / 解密失败 / 读不到）。

    仅服务于**旁路** run 级事件审计（RunEventAuditor）：审计器捕获后统一降级为
    `inconclusive` 并把本异常消息作为原因，绝不打断 run、绝不冒充「没发现问题」
    （硬约束 #6 / #10）。case 级 check() 路径不使用本异常，保持既有 inconclusive 降级。
    """


class LogVerifyBackend(Protocol):
    """一路 DLP 日志验证后端。由 DlpLogChecker 门面按平台选用后并全权委托。"""

    def on_case_start(self, ctx: CheckContext) -> None:  # pragma: no cover
        ...

    def check(self, ctx: CheckContext) -> CheckOutcome:  # pragma: no cover
        ...

    # 旁路事件审计用的**只读**收集接口（默认可选；未实现的后端由审计器判 inconclusive）。
    # 复用各平台既有「解密 → 时间窗过滤」，只多做一个 window_end 上界过滤。
    def collect_events(self, window_start, window_end) -> "list[DlpEvent]":  # pragma: no cover
        ...


def parse_line_ts(line: str) -> Optional[datetime]:
    """解析行首 [YYYY-MM-DD HH:MM:SS(.mmm)] 时间戳；无法解析返回 None。"""
    m = _TS_RE.match(line)
    if not m:
        return None
    base = m.group(1)
    micro = m.group(2)
    try:
        dt = datetime.strptime(base, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    if micro:
        # 右侧补零到微秒（6 位）
        dt = dt.replace(microsecond=int(micro.ljust(6, "0")[:6]))
    return dt


def _extract(pattern: str, text: str) -> str:
    m = re.search(pattern, text)
    return m.group(1).strip() if m else ""


def parse_event_line(line: str) -> DlpEvent:
    """把一条真实事件行解析为 DlpEvent（字段取不到时留空，不抛异常）。

    仅负责解析，**不判断**这行是不是真事件——调用方须先用 event_marker + 事件UUID
    锚定过（见 _windows.py），以规避把宿主 shell 回显误当事件。
    """
    return DlpEvent(
        raw_line=line.rstrip("\r\n"),
        ts=parse_line_ts(line),
        event_uuid=_extract(r"事件UUID\s*[:：]\s*([0-9a-fA-F-]{8,})", line),
        process_name=_extract(r"process name is\s+([^\s|]+)", line),
        origin_file_path=_extract(r"origin file path is\s+(.+?)\s*$", line),
        tag_name=_extract(r"tag name is\s+([^\s|]+)", line),
    )
