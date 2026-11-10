"""多轮 history 管理（迁自 ai-ui/uitars_run.py 的 TurnRecord + 历史裁剪）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TurnRecord:
    step: int
    action: Any            # 模型输出的 action 行 / action dict
    observation: str       # 执行结果描述


def compress_history(history: list[TurnRecord], keep: int = 10) -> list[TurnRecord]:
    """仅保留最近 keep 步，防止 context 过长。"""
    if keep <= 0 or len(history) <= keep:
        return list(history)
    return history[-keep:]
