from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from dlp_auto.case.runner import CaseRunner
from dlp_auto.case.spec import CaseSpec, ai, step
from dlp_auto.config import Settings
from dlp_auto.core.agent import Agent
from dlp_auto.core.judge import Verdict
from dlp_auto.core.platform import CURRENT
from dlp_auto.core.run_context import RunContext
from dlp_auto.llm import build_registry
from dlp_auto.report.schema import CaseReport
from dlp_auto.report.writer import ReportWriter
from dlp_auto.verify.aggregator import OutcomeAggregator
from dlp_auto.verify.dlp_log import DlpLogChecker
from dlp_auto.verify.manager import VerificationManager
from dlp_auto.verify.outcome import CheckContext, CheckOutcome
from dlp_auto.verify.server_event import ServerEventChecker


def _report() -> CaseReport:
    return CaseReport(
        id="case.demo",
        name="demo",
        channel="desktop_app.im",
        platform="mac",
    )


def _context(root: str | Path = ".") -> RunContext:
    root = Path(root)
    return RunContext(
        run_id=RunContext.new_run_id(),
        platform=CURRENT,
        settings=Settings(),
        report_dir=root / "reports",
        log_dir=root / "logs",
        screenshot_root=root / "screenshots" / "final",
    )


class _FinishedLlm:
    def __init__(self):
        self.calls = 0

    def chat(self, _messages):
        self.calls += 1
        return '{"type":"finished"}'


class _Screen:
    def __init__(self):
        self.calls = 0

    def capture(self, **_kwargs):
        self.calls += 1
        return SimpleNamespace(b64=f"shot-{self.calls}")


class _Executor:
    def __init__(self):
        self.calls = 0

    def do(self, _action):
        self.calls += 1
        return True, "finished"


class _Judge:
    def __init__(self, verdict: Verdict):
        self.verdict = verdict
        self.calls = 0
        self.images: list[tuple[str, str]] = []

    def verify(self, _assertion, before_b64, after_b64):
        self.calls += 1
        self.images.append((before_b64, after_b64))
        return self.verdict


class ResultTrustTests(unittest.TestCase):
    def test_conclusive_control_check_can_pass(self):
        class PassingChecker:
            name = "dlp_log"

            @staticmethod
            def check(_ctx):
                return CheckOutcome("dlp_log", "passed", "matched")

        rep = _report()
        manager = VerificationManager(case_checkers=[PassingChecker()])
        manager.on_case_finished(CheckContext(case=SimpleNamespace(id=rep.id),
                                              rep=rep))

        self.assertEqual(rep.execution_status, "passed")
        self.assertEqual(rep.verification_status, "passed")
        self.assertEqual(rep.status, "passed")

    def test_no_control_check_cannot_pass(self):
        rep = _report()
        rep.execution_status = "passed"
        VerificationManager().finalize(rep)

        self.assertEqual(rep.status, "inconclusive")
        self.assertEqual(rep.verification_status, "skipped")
        self.assertIn("未启用", rep.issue)

    def test_runner_without_verifier_cannot_pass(self):
        case = CaseSpec(
            id="case.no-verifier",
            name="no verifier",
            channel="desktop_app.im",
            platforms=[CURRENT],
            define=list,
        )

        rep = CaseRunner(context=_context()).run_one(case)

        self.assertEqual(rep.execution_status, "passed")
        self.assertEqual(rep.status, "inconclusive")

    def test_server_mock_is_inconclusive(self):
        # 服务端回查已改为 run 级：mock 下有 event_id 的 case 恒 inconclusive（仅验证链路）。
        from dlp_auto.report.schema import RunReport
        rep = _report()
        rep.event_id = "uuid-demo"
        run = RunReport(run_id="r", cases=[rep])

        outcome = ServerEventChecker(mock=True).check_run(run)[rep.id]

        self.assertEqual(outcome.status, "inconclusive")
        self.assertTrue(outcome.evidence["mocked"])


class JudgeSafetyTests(unittest.TestCase):
    @staticmethod
    def _llm_config(model: str) -> dict:
        return {
            "provider": "ark_doubao",
            "base_url": "https://example.invalid/v1",
            "api_key": "test-key",
            "model": model,
        }

    def test_judge_endpoint_falls_back_to_default_when_omitted(self):
        registry = build_registry(Settings(raw={
            "llm": {"default": self._llm_config("agent-model")},
        }))

        self.assertIs(registry.judge, registry.default)

    def test_judge_endpoint_can_use_an_independent_provider(self):
        registry = build_registry(Settings(raw={
            "llm": {
                "default": self._llm_config("agent-model"),
                "judge": self._llm_config("judge-model"),
            },
        }))

        self.assertIsNot(registry.judge, registry.default)
        self.assertEqual(registry.default.model, "agent-model")
        self.assertEqual(registry.judge.model, "judge-model")

    def test_unwired_step_judge_is_rejected_instead_of_silently_passing(self):
        class LegacyStepJudge:
            @staticmethod
            def evaluate(_ctx):
                raise AssertionError(f"不应执行: {_ctx}")

        with self.assertRaises(TypeError):
            step("旧断言", LegacyStepJudge())

    def test_ai_verify_remains_the_supported_visual_judge_entry(self):
        visual_step = step("发送文件", ai("发送文件", verify="出现新增文件消息"))

        self.assertEqual(visual_step.kind, "ai")
        self.assertEqual(visual_step.verify, "出现新增文件消息")

    def test_inconclusive_judge_retries_only_judge(self):
        executor = _Executor()
        judge = _Judge(Verdict("inconclusive", "invalid judge json"))
        agent = Agent(
            _FinishedLlm(),
            executor,
            _Screen(),
            judge=judge,
            step_wait_sec=0,
            max_verify_retries=2,
        )

        result = agent.do("发送文件", verify="新增文件消息")

        self.assertTrue(result.ok)
        self.assertEqual(result.verify_status, "inconclusive")
        self.assertEqual(executor.calls, 1)
        self.assertEqual(judge.calls, 3)
        self.assertEqual(len(set(judge.images)), 1)

    def test_failed_judge_does_not_retry_action_by_default(self):
        executor = _Executor()
        judge = _Judge(Verdict("failed", "未看到新增文件消息"))
        agent = Agent(
            _FinishedLlm(),
            executor,
            _Screen(),
            judge=judge,
            step_wait_sec=0,
            max_verify_retries=2,
        )

        result = agent.do("发送文件", verify="新增文件消息")

        self.assertFalse(result.ok)
        self.assertEqual(result.verify_status, "failed")
        self.assertEqual(executor.calls, 1)
        self.assertEqual(judge.calls, 1)

    def test_before_step_guard_runs_before_every_capture(self):
        calls: list[int] = []
        screen = _Screen()
        agent = Agent(
            _FinishedLlm(),
            _Executor(),
            screen,
            step_wait_sec=0,
        )

        result = agent.do(
            "检查受管窗口",
            before_step=lambda: calls.append(screen.calls),
        )

        self.assertTrue(result.ok)
        self.assertEqual(calls, [0])
        self.assertEqual(screen.calls, 1)


class ActionLimitTests(unittest.TestCase):
    class _SequenceLlm:
        def __init__(self, responses):
            self.responses = iter(responses)

        def chat(self, _messages):
            return next(self.responses)

    class _RecordingExecutor:
        def __init__(self):
            self.actions: list[str] = []

        def do(self, action):
            action_type = action["type"]
            self.actions.append(action_type)
            return action_type in {"finished", "call_user"}, action_type

    def test_repeated_limited_action_is_blocked_before_executor(self):
        executor = self._RecordingExecutor()
        agent = Agent(
            self._SequenceLlm([
                '{"type":"click","start":[500,500]}',
                '{"type":"click","start":[500,500]}',
                '{"type":"finished"}',
            ]),
            executor,
            _Screen(),
            step_wait_sec=0,
            max_steps=3,
        )

        result = agent.do("Submit 只点击一次", action_limits={"click": 1})

        self.assertTrue(result.ok)
        self.assertEqual(executor.actions, ["click", "finished"])
        self.assertIn("action_blocked", result.trajectory[1].observation)

    def test_ai_action_limits_propagate_to_step(self):
        limited = step(
            "提交",
            ai("只提交一次", action_limits={"click": 1, "scroll": 1}),
        )

        self.assertEqual(limited.action_limits, {"click": 1, "scroll": 1})

    def test_ai_rejects_non_positive_action_limit(self):
        with self.assertRaisesRegex(ValueError, "大于等于 1"):
            ai("错误配置", action_limits={"click": 0})


class PresenceVerifyTests(unittest.TestCase):
    """verify_mode="presence"：只看 after 单图存在性，不做 before/after 对比。

    用于 auto-send 场景（文件在更早步骤/拖拽释放瞬间已发出），规避同图假 fail。
    """

    class _PresenceJudge:
        """记录 change/presence 两条路各自的调用与入参图片，供断言分派是否正确。"""

        def __init__(self, verdict: Verdict):
            self.verdict = verdict
            self.change_calls = 0
            self.presence_calls = 0
            self.presence_images: list[str] = []

        def verify(self, _assertion, _before, _after):
            self.change_calls += 1
            return self.verdict

        def verify_presence(self, _assertion, after_b64):
            self.presence_calls += 1
            self.presence_images.append(after_b64)
            return self.verdict

    def test_presence_mode_routes_to_single_image_judge(self):
        judge = self._PresenceJudge(Verdict("passed", "看到唯一文件名气泡"))
        agent = Agent(_FinishedLlm(), _Executor(), _Screen(),
                      judge=judge, step_wait_sec=0, max_verify_retries=1)

        result = agent.do("拖拽发送文件", verify="聊天区存在唯一文件名气泡",
                          verify_mode="presence")

        self.assertTrue(result.ok)
        self.assertEqual(result.verify_status, "passed")
        # 只走 presence 路（单图），绝不走 before/after 对比路
        self.assertEqual(judge.presence_calls, 1)
        self.assertEqual(judge.change_calls, 0)
        self.assertEqual(len(judge.presence_images), 1)

    def test_default_mode_still_uses_before_after(self):
        judge = self._PresenceJudge(Verdict("passed", "新增气泡"))
        agent = Agent(_FinishedLlm(), _Executor(), _Screen(),
                      judge=judge, step_wait_sec=0, max_verify_retries=1)

        agent.do("发送文件", verify="新增文件消息")  # 不传 verify_mode → 默认 change

        self.assertEqual(judge.change_calls, 1)
        self.assertEqual(judge.presence_calls, 0)

    def test_ai_verify_mode_propagates_to_step(self):
        from dlp_auto.case.spec import step as make_step

        s_default = make_step("s1", ai("i", verify="v"))
        s_presence = make_step("s2", ai("i", verify="v", verify_mode="presence"))
        self.assertEqual(s_default.verify_mode, "change")
        self.assertEqual(s_presence.verify_mode, "presence")


class ScreenFailSafeMarginTests(unittest.TestCase):
    """to_px 必须把落点收进离屏幕四边的安全边距，避免贴角坐标踩中 pyautogui fail-safe。"""

    def _to_px(self, norm_xy, size=(2560, 1600)):
        import pyautogui

        from dlp_auto.core.screen import Screen
        orig = pyautogui.size
        pyautogui.size = lambda: size
        try:
            return Screen().to_px(norm_xy)
        finally:
            pyautogui.size = orig

    def test_top_left_corner_is_pushed_off_the_edge(self):
        from dlp_auto.core.screen import _EDGE_MARGIN_PX

        x, y = self._to_px((0, 0))
        # (0,0) 归一化不能落到像素 (0,0)（fail-safe 角点），至少离边 _EDGE_MARGIN_PX
        self.assertEqual((x, y), (_EDGE_MARGIN_PX, _EDGE_MARGIN_PX))

    def test_bottom_right_corner_is_pushed_off_the_edge(self):
        from dlp_auto.core.screen import _EDGE_MARGIN_PX

        w, h = 2560, 1600
        x, y = self._to_px((1000, 1000), size=(w, h))
        self.assertEqual((x, y), (w - 1 - _EDGE_MARGIN_PX, h - 1 - _EDGE_MARGIN_PX))

    def test_center_is_unaffected(self):
        # 非贴边坐标不受边距影响，换算照旧
        self.assertEqual(self._to_px((500, 500), size=(2560, 1600)), (1280, 800))


class ArtifactIsolationTests(unittest.TestCase):
    def test_run_ids_are_unique(self):
        self.assertNotEqual(
            RunContext.new_run_id(),
            RunContext.new_run_id(),
        )

    def test_run_context_owns_artifact_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = _context(tmp)

            self.assertEqual(
                context.report_path,
                Path(tmp) / "reports" / f"{context.run_id}.csv",
            )
            self.assertEqual(
                context.log_path,
                Path(tmp) / "logs" / f"run_{context.run_id}.log",
            )
            self.assertEqual(
                context.screenshot_path("case/demo name"),
                Path(tmp) / "screenshots" / "final"
                / context.run_id / "case_demo_name.png",
            )

    def test_incremental_report_refuses_existing_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer = ReportWriter(out_dir=tmp)
            writer.open_incremental("same-run")
            writer.close_incremental()

            second = ReportWriter(out_dir=tmp)
            with self.assertRaises(FileExistsError):
                second.open_incremental("same-run")

            path = Path(tmp) / "same-run.csv"
            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 0)


class OutcomeAggregatorTests(unittest.TestCase):
    def test_execution_failure_has_priority_over_checks(self):
        result = OutcomeAggregator.aggregate(
            execution_status="failed",
            checks={"dlp_log": {"status": "passed"}},
            expected_names=["dlp_log"],
            existing_issue="动作失败",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.verification_status, "skipped")
        self.assertEqual(result.issue, "动作失败")

    def test_requires_every_expected_check_passed(self):
        result = OutcomeAggregator.aggregate(
            execution_status="passed",
            checks={"dlp_log": {"status": "passed"}},
            expected_names=["dlp_log", "server_event"],
        )

        self.assertEqual(result.status, "inconclusive")
        self.assertEqual(result.verification_status, "inconclusive")
        self.assertIn("server_event=missing", result.issue)


class PolicyAggregatorTests(unittest.TestCase):
    """策略感知聚合（P0）：none 零回归 / audit 判定表 / block 占位。"""

    def test_none_ignores_delivery_outcome(self):
        # policy=none 时 delivery_outcome 完全不参与，逐字节回退现状。
        with_delivery = OutcomeAggregator.aggregate(
            execution_status="passed",
            checks={"dlp_log": {"status": "passed"}},
            expected_names=["dlp_log"],
            policy="none",
            delivery_outcome="blocked",
        )
        baseline = OutcomeAggregator.aggregate(
            execution_status="passed",
            checks={"dlp_log": {"status": "passed"}},
            expected_names=["dlp_log"],
        )
        self.assertEqual(with_delivery, baseline)
        self.assertEqual(with_delivery.status, "passed")

    def test_audit_sent_with_matching_log_passes(self):
        result = OutcomeAggregator.aggregate(
            execution_status="passed",
            checks={"dlp_log": {"status": "passed"}},
            expected_names=["dlp_log"],
            policy="audit",
            delivery_outcome="sent",
        )
        self.assertEqual(result.status, "passed")
        self.assertEqual(result.verification_status, "passed")

    def test_audit_execution_failure_cannot_be_overridden_by_sent_and_log(self):
        result = OutcomeAggregator.aggregate(
            execution_status="failed",
            checks={"dlp_log": {"status": "passed"}},
            expected_names=["dlp_log"],
            policy="audit",
            delivery_outcome="sent",
            existing_issue="附件预览确认失败",
        )
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.verification_status, "skipped")
        self.assertEqual(result.issue, "附件预览确认失败")

    def test_audit_sent_without_log_is_inconclusive(self):
        # 外发成功但没开日志验收 → 不下「没问题」结论（硬约束）。
        result = OutcomeAggregator.aggregate(
            execution_status="passed",
            checks={},
            expected_names=[],
            policy="audit",
            delivery_outcome="sent",
        )
        self.assertEqual(result.status, "inconclusive")
        self.assertEqual(result.verification_status, "skipped")

    def test_audit_sent_with_failed_log_fails(self):
        result = OutcomeAggregator.aggregate(
            execution_status="passed",
            checks={"dlp_log": {"status": "failed", "detail": "无日志"}},
            expected_names=["dlp_log"],
            policy="audit",
            delivery_outcome="sent",
        )
        self.assertEqual(result.status, "failed")

    def test_audit_blocked_fails(self):
        # 审计策略下文件被拦截 → 与预期不符，判 failed。
        result = OutcomeAggregator.aggregate(
            execution_status="passed",
            checks={"dlp_log": {"status": "passed"}},
            expected_names=["dlp_log"],
            policy="audit",
            delivery_outcome="blocked",
        )
        self.assertEqual(result.status, "failed")
        self.assertIn("拦截", result.issue)

    def test_audit_unknown_delivery_is_inconclusive(self):
        result = OutcomeAggregator.aggregate(
            execution_status="passed",
            checks={"dlp_log": {"status": "passed"}},
            expected_names=["dlp_log"],
            policy="audit",
            delivery_outcome="unknown",
        )
        self.assertEqual(result.status, "inconclusive")

    def test_audit_error_short_circuits(self):
        result = OutcomeAggregator.aggregate(
            execution_status="error",
            checks={},
            expected_names=["dlp_log"],
            policy="audit",
            delivery_outcome="unknown",
            existing_issue="崩了",
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.verification_status, "skipped")
        self.assertEqual(result.issue, "崩了")

    def test_block_blocked_with_block_log_passes(self):
        # 已拦截 + 命中阻断日志（checker 已判 passed）→ 双证据齐全，passed
        result = OutcomeAggregator.aggregate(
            execution_status="passed",
            checks={"dlp_log": {"status": "passed"}},
            expected_names=["dlp_log"],
            policy="block",
            delivery_outcome="blocked",
        )
        self.assertEqual(result.status, "passed")
        self.assertEqual(result.verification_status, "passed")

    def test_block_execution_failure_cannot_be_overridden_by_block_log(self):
        result = OutcomeAggregator.aggregate(
            execution_status="failed",
            checks={"dlp_log": {"status": "passed"}},
            expected_names=["dlp_log"],
            policy="block",
            delivery_outcome="blocked",
            existing_issue="阻断界面判断失败",
        )
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.verification_status, "skipped")
        self.assertEqual(result.issue, "阻断界面判断失败")

    def test_block_blocked_with_audit_log_fails(self):
        # 已拦截但命中的是审计类日志（checker 已判 failed=错配）→ failed
        result = OutcomeAggregator.aggregate(
            execution_status="passed",
            checks={"dlp_log": {"status": "failed", "detail": "命中审计类特征"}},
            expected_names=["dlp_log"],
            policy="block",
            delivery_outcome="blocked",
        )
        self.assertEqual(result.status, "failed")

    def test_block_blocked_without_log_is_inconclusive(self):
        # 情况一：已拦截但无阻断日志铁证（checker 判 inconclusive）→ 不下确定结论
        result = OutcomeAggregator.aggregate(
            execution_status="passed",
            checks={"dlp_log": {"status": "inconclusive"}},
            expected_names=["dlp_log"],
            policy="block",
            delivery_outcome="blocked",
        )
        self.assertEqual(result.status, "inconclusive")

    def test_block_sent_fails_regardless_of_log(self):
        # 情况二：文件竟被发出 = 阻断失效 = 泄露，日志无翻案权，直接 failed
        result = OutcomeAggregator.aggregate(
            execution_status="passed",
            checks={"dlp_log": {"status": "passed"}},
            expected_names=["dlp_log"],
            policy="block",
            delivery_outcome="sent",
        )
        self.assertEqual(result.status, "failed")
        self.assertIn("发出", result.issue)

    def test_block_unknown_delivery_is_inconclusive(self):
        # 外发结果未知 → 连拦没拦住都不确定，inconclusive
        result = OutcomeAggregator.aggregate(
            execution_status="passed",
            checks={"dlp_log": {"status": "passed"}},
            expected_names=["dlp_log"],
            policy="block",
            delivery_outcome="unknown",
        )
        self.assertEqual(result.status, "inconclusive")

    def test_block_error_short_circuits(self):
        # 自动化异常与外发结果无关 → 短路保留 error
        result = OutcomeAggregator.aggregate(
            execution_status="error",
            checks={},
            expected_names=["dlp_log"],
            policy="block",
            delivery_outcome="unknown",
            existing_issue="崩了",
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.verification_status, "skipped")
        self.assertEqual(result.issue, "崩了")

    def test_manager_infers_delivery_from_visual_under_policy(self):
        # policy=audit 下，视觉 passed → delivery=sent；配合日志通过 → passed。
        class PassingChecker:
            name = "dlp_log"

            @staticmethod
            def check(_ctx):
                return CheckOutcome("dlp_log", "passed", "matched")

        rep = _report()
        rep.extras["checks"] = {
            "visual": {"name": "visual", "status": "passed", "detail": ""}
        }
        manager = VerificationManager(case_checkers=[PassingChecker()],
                                      policy="audit")
        manager.on_case_finished(CheckContext(case=SimpleNamespace(id=rep.id),
                                              rep=rep))

        self.assertEqual(rep.delivery_outcome, "sent")
        self.assertEqual(rep.status, "passed")

    def test_manager_none_policy_leaves_delivery_empty(self):
        rep = _report()
        rep.extras["checks"] = {
            "visual": {"name": "visual", "status": "passed", "detail": ""}
        }
        VerificationManager(policy="none").finalize(rep)
        self.assertEqual(rep.delivery_outcome, "")


class _RecordingLlm:
    """始终 finished，但记录每次 chat 收到的 messages，供断言回灌话术。"""

    def __init__(self):
        self.calls = 0
        self.message_batches: list = []

    def chat(self, messages):
        self.calls += 1
        self.message_batches.append(messages)
        return '{"type":"finished"}'


def _joined(messages) -> str:
    return "\n".join(str(m.get("content", "")) for m in messages)


class RetryHintPolicyTests(unittest.TestCase):
    """P1 重试联动（方案①′）：block 下视觉重试改自检话术，不诱导重发。"""

    def test_none_and_audit_keep_original_retry_hint(self):
        for policy in ("none", "audit"):
            hint = Agent._retry_hint("未看到新增消息", policy)
            self.assertIn("继续操作以达成目标", hint)
            self.assertNotIn("阻断策略", hint)

    def test_block_uses_self_check_and_forbids_resend(self):
        hint = Agent._retry_hint("未看到新增消息", "block")
        self.assertIn("阻断策略", hint)
        self.assertIn("不要重复发送", hint)
        # 关键：不得出现诱导「继续外发达成目标」的原话术
        self.assertNotIn("继续操作以达成目标", hint)

    def test_block_retry_feeds_self_check_wording_to_model(self):
        llm = _RecordingLlm()
        judge = _Judge(Verdict("failed", "文件疑似被拦截"))
        agent = Agent(llm, _Executor(), _Screen(), judge=judge,
                      step_wait_sec=0, max_verify_retries=1)

        agent.do("拖拽发送文件", verify="出现新增文件消息",
                 retry_on_verify_fail=True, policy="block")

        # 触发了一次重试（首轮 finished 被判 failed → 回灌 → 再来一轮）
        self.assertGreaterEqual(llm.calls, 2)
        last = _joined(llm.message_batches[-1])
        self.assertIn("不要重复发送", last)
        self.assertNotIn("继续操作以达成目标", last)

    def test_default_policy_retry_keeps_original_wording(self):
        llm = _RecordingLlm()
        judge = _Judge(Verdict("failed", "未看到新增消息"))
        agent = Agent(llm, _Executor(), _Screen(), judge=judge,
                      step_wait_sec=0, max_verify_retries=1)

        agent.do("发送文件", verify="出现新增消息",
                 retry_on_verify_fail=True)  # policy 默认 none

        self.assertGreaterEqual(llm.calls, 2)
        last = _joined(llm.message_batches[-1])
        self.assertIn("继续操作以达成目标", last)
        self.assertNotIn("阻断策略", last)


class LogPolicyTypingTests(unittest.TestCase):
    """②日志分型：dlp_log checker 按 policy 选特征并产出 hit_policy_type。"""

    def _run(self, *, policy, log_text, spec=None,
             default_contains=None,
             default_audit_contains=None, default_block_contains=None):
        """在临时日志文件上跑一次 DlpLogChecker.check，返回 CheckOutcome。"""
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "dlp.log"
            log_path.write_text(log_text, encoding="utf-8")
            checker = DlpLogChecker(
                path=str(log_path),
                default_contains=default_contains,
                default_audit_contains=default_audit_contains,
                default_block_contains=default_block_contains,
                cases={"case.demo": spec} if spec else {},
            )
            ctx = CheckContext(case=SimpleNamespace(id="case.demo"),
                               rep=_report(), policy=policy)
            # 起点偏移=0，读取整份日志窗口
            ctx.extras["dlp_log_start_offset"] = 0
            return checker.check(ctx)

    def test_none_policy_generic_match_has_no_hit_policy_type(self):
        # 零回归：policy=none 走通用特征，命中 passed 且不写 hit_policy_type
        outcome = self._run(policy="none", log_text="outbound file sent\n",
                            default_contains="outbound file")
        self.assertEqual(outcome.status, "passed")
        self.assertNotIn("hit_policy_type", outcome.evidence)

    def test_audit_hits_audit_feature_passes(self):
        outcome = self._run(
            policy="audit", log_text="event action=AUDIT file=a.doc\n",
            default_audit_contains="action=AUDIT",
            default_block_contains="action=BLOCK")
        self.assertEqual(outcome.status, "passed")
        self.assertEqual(outcome.evidence.get("hit_policy_type"), "audit")

    def test_audit_hits_block_feature_fails_as_mismatch(self):
        # 命中的是另一种（block）类型 → 错配 failed，hit_policy_type=block
        outcome = self._run(
            policy="audit", log_text="event action=BLOCK file=a.doc\n",
            default_audit_contains="action=AUDIT",
            default_block_contains="action=BLOCK")
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.evidence.get("hit_policy_type"), "block")

    def test_block_hits_block_feature_passes(self):
        outcome = self._run(
            policy="block", log_text="event action=BLOCK file=a.doc\n",
            default_audit_contains="action=AUDIT",
            default_block_contains="action=BLOCK")
        self.assertEqual(outcome.status, "passed")
        self.assertEqual(outcome.evidence.get("hit_policy_type"), "block")

    def test_typed_mode_missing_current_feature_is_inconclusive(self):
        # 已启用分型（配了 block），但当前 policy=audit 缺 audit 特征 →
        # inconclusive，绝不回退通用特征假通过
        outcome = self._run(
            policy="audit", log_text="outbound file sent\n",
            default_contains="outbound file",
            default_block_contains="action=BLOCK")
        self.assertEqual(outcome.status, "inconclusive")
        self.assertIsNone(outcome.evidence.get("hit_policy_type"))

    def test_block_typed_no_match_is_inconclusive(self):
        # block 未命中阻断日志 → 缺铁证，判 inconclusive（§4.3 情况一），不冤枉判失败
        outcome = self._run(
            policy="block", log_text="nothing relevant here\n",
            default_audit_contains="action=AUDIT",
            default_block_contains="action=BLOCK")
        self.assertEqual(outcome.status, "inconclusive")
        self.assertIsNone(outcome.evidence.get("hit_policy_type"))

    def test_audit_typed_no_match_fails(self):
        # audit 未命中审计日志 → 应留痕却没有，审计失效判 failed
        outcome = self._run(
            policy="audit", log_text="nothing relevant here\n",
            default_audit_contains="action=AUDIT",
            default_block_contains="action=BLOCK")
        self.assertEqual(outcome.status, "failed")
        self.assertIsNone(outcome.evidence.get("hit_policy_type"))

    def test_compat_mode_generic_only_marks_unknown(self):
        # policy=audit 但只配了通用特征（无分型）→ 兼容模式，命中记 unknown
        outcome = self._run(
            policy="audit", log_text="outbound file sent\n",
            default_contains="outbound file")
        self.assertEqual(outcome.status, "passed")
        self.assertEqual(outcome.evidence.get("hit_policy_type"), "unknown")

    def test_case_level_feature_overrides_default(self):
        # case 级分型特征优先于 default_*
        outcome = self._run(
            policy="block",
            log_text="event action=BLOCK file_id=42\n",
            spec={"block_contains": "action=BLOCK"},
            default_block_contains="action=NOPE")
        self.assertEqual(outcome.status, "passed")
        self.assertEqual(outcome.evidence.get("hit_policy_type"), "block")


class PolicyConfigValidationTests(unittest.TestCase):
    """build_manager 对非法 policy 值应报错，不静默回退 none。"""

    def test_invalid_config_policy_raises(self):
        from dlp_auto.verify import build_manager
        settings = Settings(raw={"verify": {"policy": "audi"}})
        with self.assertRaises(ValueError):
            build_manager(settings)

    def test_valid_config_policy_is_accepted(self):
        from dlp_auto.verify import build_manager
        settings = Settings(raw={"verify": {"policy": "audit"}})
        manager = build_manager(settings)
        self.assertEqual(manager.policy, "audit")


if __name__ == "__main__":
    unittest.main()
