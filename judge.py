"""独立验收（Judge）：基于 before/after 两张截图判断操作是否真的生效。

解决"假性 finished"：agent 自报 finished 不等于任务真的完成。
Judge 用一个独立 LLM，对比执行前后的界面变化来裁决，而不是只看现状。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal

from dlp_auto.llm.ark_doubao import ArkDoubaoProvider
from dlp_auto.llm.prompts import SYSTEM_PROMPT_JUDGE, SYSTEM_PROMPT_JUDGE_PRESENCE


@dataclass
class Verdict:
    status: Literal["passed", "failed", "inconclusive"]
    reason: str = ""

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    @property
    def inconclusive(self) -> bool:
        return self.status == "inconclusive"


class Judge:
    def __init__(self, llm):
        self.llm = llm

    def verify(self, assertion: str, before_b64: str, after_b64: str) -> Verdict:
        """对比 before/after，裁决 assertion 描述的变化是否发生。"""
        text = (
            "验收标准（这次操作应当带来的变化）：\n"
            f"{assertion}\n\n"
            "第 1 张图是操作之前(before)，第 2 张图是操作之后(after)。"
            "请基于两图的变化作出裁决。"
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_JUDGE},
            ArkDoubaoProvider.user_message_with_images(text, [before_b64, after_b64]),
        ]
        raw = self.llm.chat(messages, max_tokens=300)
        print(f"  🔎 验收模型返回：{(raw or '').strip()}")
        return self._parse(raw)

    def verify_presence(self, assertion: str, after_b64: str) -> Verdict:
        """只看 after 单图，裁决 assertion 描述的目标物是否**存在**（不做 before/after 对比）。

        用于 auto-send 场景：外发动作在更早的 hard step / 拖拽释放瞬间就已发生，before/after
        必是同一张「已发出」图，change 模式必假 fail（见 LESSONS #11/#12）。presence 模式配合
        唯一文件名验收，判「该唯一标识的目标物此刻是否在界面上」，出现即为本次所产生。
        """
        text = (
            "验收标准（此刻界面上应当存在的目标物）：\n"
            f"{assertion}\n\n"
            "这是操作之后(after)的界面截图。请判断上述目标物在这张图里是否存在。"
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_JUDGE_PRESENCE},
            ArkDoubaoProvider.user_message_with_images(text, [after_b64]),
        ]
        raw = self.llm.chat(messages, max_tokens=300)
        print(f"  🔎 验收模型返回（presence）：{(raw or '').strip()}")
        return self._parse(raw)

    @staticmethod
    def _parse(raw: str) -> Verdict:
        text = (raw or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\n?|```$", "", text).strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return Verdict("inconclusive", f"无法解析裁决输出：{text[:80]}")
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            return Verdict("inconclusive", f"裁决 JSON 解析失败：{text[:80]}")
        if not isinstance(obj, dict):
            return Verdict("inconclusive", "裁决输出非对象")
        passed = obj.get("passed")
        if not isinstance(passed, bool):
            return Verdict("inconclusive", "裁决输出缺少布尔型 passed 字段")
        return Verdict(
            "passed" if passed else "failed",
            str(obj.get("reason", "")),
        )
