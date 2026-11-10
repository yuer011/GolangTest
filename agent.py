"""Agent 主循环：感知 -> 决策 -> 执行（迁自 ai-ui/uitars_run.py 的 run 循环）。

依赖注入：llm(ArkDoubaoProvider) / executor(Executor) / screen(Screen)。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from dlp_auto.core.history import TurnRecord, compress_history
from dlp_auto.core.parser import ParserError, parse_action
from dlp_auto.llm.ark_doubao import ArkDoubaoProvider
from dlp_auto.llm.prompts import SYSTEM_PROMPT_AGENT


@dataclass
class StepResult:
    ok: bool
    reason: str = ""
    steps: int = 0
    trajectory: list = field(default_factory=list)
    # 视觉验收（block①）结论冒泡：None=未设 verify；否则三态
    # passed/failed/inconclusive。
    verify_status: str | None = None
    verify_reason: str = ""


class Agent:
    def __init__(self, llm, executor, screen, *, max_steps: int = 30,
                 step_wait_sec: float = 0.9, fallback_text: bool = True,
                 history_keep: int = 10, capture_each_step: bool = False,
                 judge=None, max_verify_retries: int = 2,
                 max_parse_retries: int = 3):
        self.llm = llm
        self.executor = executor
        self.screen = screen
        self.max_steps = max_steps
        self.step_wait_sec = step_wait_sec
        self.fallback_text = fallback_text
        self.history_keep = history_keep
        self.capture_each_step = capture_each_step
        self.judge = judge
        self.max_verify_retries = max_verify_retries
        # 连续解析失败达到此值即提前判败，避免白烧 max_steps
        self.max_parse_retries = max_parse_retries

    def do(self, instruction: str, ctx=None, *, hints: list[str] | None = None,
           verify: str | None = None,
           retry_on_verify_fail: bool = False,
           verify_mode: str = "change",
           action_limits: dict[str, int] | None = None,
           before_step=None,
           policy: str = "none") -> StepResult:
        history: list[TurnRecord] = []
        effective = self._apply_hints(instruction, hints)
        before_b64: str | None = None
        verify_fails = 0
        parse_fails = 0
        limits = dict(action_limits or {})
        action_counts: dict[str, int] = {}
        blocked_counts: dict[str, int] = {}

        for step in range(1, self.max_steps + 1):
            if before_step is not None:
                before_step()
            shot = self.screen.capture(persist=self.capture_each_step,
                                       name=f"step_{step:03d}")
            if before_b64 is None:
                before_b64 = shot.b64
            messages = self._build_messages(effective, history, shot.b64)

            raw = self.llm.chat(messages)
            print(f"\n===== STEP {step} =====\n{raw}")

            try:
                action = parse_action(raw, fallback_text=self.fallback_text)
                parse_fails = 0  # 成功解析即清零，只拦「连续」失败
            except ParserError as e:
                parse_fails += 1
                if parse_fails >= self.max_parse_retries:
                    return StepResult(
                        ok=False,
                        reason=f"parse_failed_{parse_fails}x: {e}",
                        steps=step, trajectory=list(history))
                # 回灌明确纠正提示，引导模型重新输出规范格式
                history.append(TurnRecord(
                    step, raw,
                    f"parse_error: {e}。上次输出格式不符，请严格按 JSON action "
                    f"格式重新输出，不要附加多余解释。"))
                history = compress_history(history, self.history_keep)
                time.sleep(self.step_wait_sec)
                continue

            action_type = str(action.get("type") or "")
            limit = limits.get(action_type)
            used = action_counts.get(action_type, 0)
            if limit is not None and used >= limit:
                blocked_counts[action_type] = blocked_counts.get(action_type, 0) + 1
                obs = (
                    f"action_blocked: {action_type} 已执行 {used} 次，"
                    f"达到本步骤上限 {limit}；本次动作未执行。"
                    "不得再次输出该动作，请根据当前画面选择 wait、finished 或 call_user。"
                )
                print(f"  -> {obs}")
                history.append(TurnRecord(step, action, obs))
                history = compress_history(history, self.history_keep)
                if blocked_counts[action_type] >= 2:
                    return StepResult(
                        ok=False,
                        reason=f"action_limit_repeated: {action_type}",
                        steps=step,
                        trajectory=list(history),
                    )
                time.sleep(self.step_wait_sec)
                continue

            is_finished, obs = self.executor.do(action)
            print(f"  -> {obs}")
            if limit is not None:
                action_counts[action_type] = used + 1

            history.append(TurnRecord(step, action, obs))
            history = compress_history(history, self.history_keep)

            if is_finished:
                ok = action.get("type") == "finished"
                if ok and self.judge is not None and verify:
                    verdict = self._verify(verify, before_b64, step,
                                           verify_mode=verify_mode)
                    if verdict.inconclusive:
                        return StepResult(
                            ok=True,
                            reason="verify_inconclusive",
                            steps=step,
                            trajectory=list(history),
                            verify_status="inconclusive",
                            verify_reason=verdict.reason,
                        )
                    if (not verdict.passed and retry_on_verify_fail
                            and verify_fails < self.max_verify_retries):
                        verify_fails += 1
                        history.append(TurnRecord(
                            step, action,
                            self._retry_hint(verdict.reason, policy)))
                        history = compress_history(history, self.history_keep)
                        time.sleep(self.step_wait_sec)
                        continue
                    if not verdict.passed:
                        return StepResult(ok=False,
                                          reason=f"verify_failed: {verdict.reason}",
                                          steps=step, trajectory=list(history),
                                          verify_status="failed",
                                          verify_reason=verdict.reason)
                    return StepResult(ok=ok, reason=action.get("type", ""),
                                      steps=step, trajectory=list(history),
                                      verify_status="passed",
                                      verify_reason=getattr(verdict, "reason", ""))
                return StepResult(ok=ok, reason=action.get("type", ""),
                                  steps=step, trajectory=list(history))

            time.sleep(self.step_wait_sec)

        return StepResult(ok=False, reason="max_steps_reached",
                          steps=self.max_steps, trajectory=list(history))

    def _verify(self, verify: str, before_b64: str, step: int,
                *, verify_mode: str = "change"):
        """冻结 before/after 后重试 Judge；绝不因基础设施故障重做 GUI 动作。

        verify_mode="presence" 时只截 after、走单图存在性裁决（auto-send 场景，见
        spec.VerifyMode / LESSONS #11/#12）；否则走历史的 before/after 变化对比。
        """
        from dlp_auto.core.judge import Verdict

        after = self.screen.capture(persist=self.capture_each_step,
                                     name=f"step_{step:03d}_after")
        verdict = Verdict("inconclusive", "Judge 未执行")
        for attempt in range(self.max_verify_retries + 1):
            try:
                if verify_mode == "presence":
                    verdict = self.judge.verify_presence(verify, after.b64)
                else:
                    verdict = self.judge.verify(verify, before_b64, after.b64)
            except Exception as e:  # noqa: BLE001
                verdict = Verdict(
                    "inconclusive",
                    f"Judge 调用异常：{type(e).__name__}: {e}",
                )
            label = {
                "passed": "通过",
                "failed": "不通过",
                "inconclusive": "未判定",
            }[verdict.status]
            print(f"  🔎 验收：{label} - {verdict.reason}")
            if not verdict.inconclusive or attempt >= self.max_verify_retries:
                return verdict
            print(f"  ⚠️ Judge 未形成有效结论，重试裁决 "
                  f"（{attempt + 1}/{self.max_verify_retries}）")
            time.sleep(self.step_wait_sec)
        return verdict

    @staticmethod
    def _retry_hint(reason: str, policy: str) -> str:
        """视觉验收未通过时回灌给模型的纠正话术。

        重试联动（P1，方案①′，见 docs/dlp_policy_assertion_design.md §4.5）：
        - policy="block"：case 的视觉 verify 多写「外发成功」语义，而阻断策略下
          文件被拦是**预期结果**，此时不能诱导模型「继续操作达成目标」（否则会逼它
          反复重发文件、白烧步数）。改为**自检话术**：只让它确认机械动作本身是否
          做到位——真没做完（如拖拽没到位/点歪）则补做，已做完就直接 finished、
          绝不重复发送。既保留「误报 finished」的恢复能力，又不逼重发。
        - 其它（none/audit）：保持历史话术，逐字节不变（零回归）。
        """
        if policy == "block":
            return (f"验收未通过：{reason}。注意：本次为阻断策略，文件被拦截可能"
                    f"正是预期结果。请只确认「外发动作本身」是否已操作到位："
                    f"若动作确实未完成（如拖拽未到位、按钮点歪），请补做该动作；"
                    f"若动作已完成，请直接 finished，不要重复发送文件。")
        return (f"验收未通过：{reason}。任务尚未真正完成，"
                f"请根据当前界面继续操作以达成目标，不要直接 finished。")

    @staticmethod
    def _apply_hints(instruction: str, hints: list[str] | None) -> str:
        if not hints:
            return instruction
        lines = "\n".join(f"- {h}" for h in hints)
        return f"{instruction}\n\n[历史成功经验，供参考以减少试探]\n{lines}"

    def _build_messages(self, instruction: str, history: list[TurnRecord],
                        image_b64: str) -> list[dict]:
        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT_AGENT}]
        for rec in history:
            messages.append({
                "role": "assistant",
                "content": f"{rec.action}\n(Result: {rec.observation})",
            })
        user_text = f"Task: {instruction}"
        if history:
            user_text += (f"\n\nStep {len(history) + 1}: "
                          f"Continue the task based on the current screenshot.")
        messages.append(ArkDoubaoProvider.user_message_with_image(user_text, image_b64))
        return messages
