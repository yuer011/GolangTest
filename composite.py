"""CompositeResolver：多渠道并行 first-win。"""
from __future__ import annotations

from typing import Any, Iterable

from .base import HumanResolver, ResumeResult


class CompositeResolver:
    name = "composite"

    def __init__(self, resolvers: Iterable[HumanResolver]):
        self.resolvers = list(resolvers)

    def wait(self, payload: Any, timeout_sec: int) -> ResumeResult:
        raise NotImplementedError("骨架阶段：CompositeResolver.wait 待 human 实装")

    def cancel(self) -> None:
        for r in self.resolvers:
            try:
                r.cancel()
            except Exception:
                pass
