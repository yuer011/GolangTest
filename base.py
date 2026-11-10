"""HumanResolver 抽象 + ResumeResult。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

ResumeDecision = Literal["approved", "rejected", "timeout", "error"]


@dataclass
class ResumeResult:
    decision: ResumeDecision
    by: str
    note: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class HumanResolver(Protocol):
    name: str

    def wait(self, payload: Any, timeout_sec: int) -> ResumeResult:  # pragma: no cover
        ...

    def cancel(self) -> None:  # pragma: no cover
        ...
