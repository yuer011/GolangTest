"""旁路 run 级 DLP 事件审计（RunEventAuditor）专项测试。

覆盖设计稿 §11 的核心用例：
- 唯一文件匹配为 expected；同名重发为 expected_retry；
- checker 命中的 UUID 直接判 expected；
- 截图 step 窗口内单条/多条（重试）；延迟截图落缓冲区判 ambiguous；同时命中多窗口判 ambiguous；
- 无归属文件/图片判 unexpected；
- UUID 去重；
- collect_events 抛错 / 后端不支持时标 inconclusive（不冒充干净）、仍写产物；
- 产物只把 ambiguous+unexpected 写进疑似误报 CSV；
- runner 集成：审计排在主报告持久化之后（硬约束 1）；auditor=None 时对 case 零影响（零回归）；
  审计崩溃不影响 case 结论/退出。
"""
from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from dlp_auto.case.runner import CaseRunner
from dlp_auto.case.spec import CaseSpec, expect_dlp, hard, step
from dlp_auto.config import Settings
from dlp_auto.core.platform import CURRENT
from dlp_auto.core.run_context import RunContext
from dlp_auto.report.schema import CaseReport
from dlp_auto.verify.dlp_log._base import DlpEvent, EventCollectError
from dlp_auto.verify.event_audit import AuditResult, RunEventAuditor

# 用明显在过去的固定基准时刻，保证 finalize_and_write 里的落盘缓冲 sleep 恒为负（不真睡）。
_BASE = datetime(2020, 1, 1, 10, 0, 0)


def _event(*, uuid: str = "", ts_offset_sec: float = 0.0,
           path: str = "", process: str = "app.exe",
           leak_name: str = "", leak_ext: str = "") -> DlpEvent:
    extras = {}
    if leak_name:
        extras["leak_file_name"] = leak_name
    if leak_ext:
        extras["leak_file_extension"] = leak_ext
    return DlpEvent(
        raw_line=f"[raw] {uuid} {path}",
        ts=_BASE + timedelta(seconds=ts_offset_sec),
        event_uuid=uuid,
        process_name=process,
        origin_file_path=path,
        extras=extras,
    )


class _FakeBackend:
    """按需返回固定事件列表；忽略窗口参数（窗口过滤是后端职责，此处直接给结果）。"""

    def __init__(self, events, image_exts=None):
        self._events = list(events)
        if image_exts is not None:
            self.image_exts = image_exts

    def collect_events(self, _window_start, _window_end):
        return list(self._events)


class _RaisingBackend:
    def collect_events(self, _window_start, _window_end):
        raise EventCollectError("解密失败：sudo 未预授权")


class _ExplodingBackend:
    def collect_events(self, _window_start, _window_end):
        raise RuntimeError("后端内部炸了")


class _NoCollectBackend:
    """没有 collect_events 的后端（如未配置解密器时的降级门面）。"""


def _auditor(backend, *, tmp, settle_sec: float = 0.0):
    ctx = SimpleNamespace(report_dir=Path(tmp), run_id="run-test")
    aud = RunEventAuditor(context=ctx, backend=backend, settle_sec=settle_sec)
    # 白盒固定四个时间点，避免真实时钟与 sleep 干扰。
    aud._run_started_at = _BASE
    aud._actions_finished_at = _BASE + timedelta(minutes=10)
    aud._event_window_finished_at = (
        _BASE + timedelta(minutes=10, seconds=settle_sec))
    return aud


def _rep(cid: str, *, sensitive_file: str = "", event_id: str = "") -> CaseReport:
    rep = CaseReport(id=cid, name=cid, channel="desktop_app.im", platform="mac")
    rep.sensitive_file = sensitive_file
    rep.event_id = event_id
    rep.started_at = _BASE.isoformat(timespec="seconds")
    rep.finished_at = (_BASE + timedelta(minutes=1)).isoformat(timespec="seconds")
    return rep


class ClassificationTests(unittest.TestCase):
    def test_unique_file_matches_expected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev = _event(uuid="u1", path="/x/dlp_sample_1.txt")
            aud = _auditor(_FakeBackend([ev]), tmp=tmp)
            result = aud.finalize_and_write([_rep("c1", sensitive_file="dlp_sample_1.txt")])
            self.assertEqual(result.status, "completed")
            self.assertEqual((result.total, result.expected), (1, 1))
            self.assertEqual(result.unexpected, 0)

    def test_same_file_repeat_is_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            evs = [
                _event(uuid="u1", ts_offset_sec=1, path="/x/dlp_sample_1.txt"),
                _event(uuid="u2", ts_offset_sec=2, path="/x/dlp_sample_1.txt"),
            ]
            aud = _auditor(_FakeBackend(evs), tmp=tmp)
            result = aud.finalize_and_write([_rep("c1", sensitive_file="dlp_sample_1.txt")])
            self.assertEqual((result.expected, result.expected_retry), (1, 1))

    def test_checker_uuid_hit_is_expected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev = _event(uuid="EVT-9", path="/x/whatever.bin")
            aud = _auditor(_FakeBackend([ev]), tmp=tmp)
            result = aud.finalize_and_write([_rep("c1", event_id="EVT-9")])
            self.assertEqual(result.expected, 1)
            self.assertEqual(result.unexpected, 0)

    def test_screenshot_single_in_window_is_expected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev = _event(uuid="u1", ts_offset_sec=30, path="screenshot.png")
            aud = _auditor(_FakeBackend([ev]), tmp=tmp)
            aud.record_expectation(
                case_id="c1", kind="image", sensitive_file="",
                started_at=_BASE + timedelta(seconds=20),
                finished_at=_BASE + timedelta(seconds=40))
            result = aud.finalize_and_write([_rep("c1")])
            self.assertEqual((result.expected, result.unexpected), (1, 0))

    def test_screenshot_retry_multiple_in_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            evs = [
                _event(uuid="u1", ts_offset_sec=25, path="screenshot.png"),
                _event(uuid="u2", ts_offset_sec=35, path="screenshot.png"),
            ]
            aud = _auditor(_FakeBackend(evs), tmp=tmp)
            aud.record_expectation(
                case_id="c1", kind="image", sensitive_file="",
                started_at=_BASE + timedelta(seconds=20),
                finished_at=_BASE + timedelta(seconds=40))
            result = aud.finalize_and_write([_rep("c1")])
            self.assertEqual((result.expected, result.expected_retry), (1, 1))

    def test_delayed_screenshot_is_ambiguous(self):
        with tempfile.TemporaryDirectory() as tmp:
            # 事件落在 step 结束后、settle 缓冲区内 → ambiguous（不直接判误报）。
            ev = _event(uuid="u1", ts_offset_sec=45, path="screenshot.png")
            aud = _auditor(_FakeBackend([ev]), tmp=tmp, settle_sec=15)
            aud.record_expectation(
                case_id="c1", kind="image", sensitive_file="",
                started_at=_BASE + timedelta(seconds=20),
                finished_at=_BASE + timedelta(seconds=40))
            result = aud.finalize_and_write([_rep("c1")])
            self.assertEqual((result.ambiguous, result.unexpected), (1, 0))

    def test_image_in_multiple_windows_is_ambiguous(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev = _event(uuid="u1", ts_offset_sec=30, path="screenshot.png")
            aud = _auditor(_FakeBackend([ev]), tmp=tmp)
            for cid in ("c1", "c2"):
                aud.record_expectation(
                    case_id=cid, kind="image", sensitive_file="",
                    started_at=_BASE + timedelta(seconds=20),
                    finished_at=_BASE + timedelta(seconds=40))
            result = aud.finalize_and_write([_rep("c1"), _rep("c2")])
            self.assertEqual(result.ambiguous, 1)

    def test_unexplained_file_is_unexpected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev = _event(uuid="u1", path="/x/some_other.docx")
            aud = _auditor(_FakeBackend([ev]), tmp=tmp)
            result = aud.finalize_and_write([_rep("c1", sensitive_file="dlp_sample_1.txt")])
            self.assertEqual(result.unexpected, 1)

    def test_unexplained_image_without_window_is_unexpected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev = _event(uuid="u1", ts_offset_sec=30, path="screenshot.png")
            aud = _auditor(_FakeBackend([ev]), tmp=tmp)  # 无任何 image 预期登记
            result = aud.finalize_and_write([_rep("c1")])
            self.assertEqual(result.unexpected, 1)

    def test_dedup_by_uuid(self):
        with tempfile.TemporaryDirectory() as tmp:
            evs = [
                _event(uuid="dup", path="/x/dlp_sample_1.txt"),
                _event(uuid="dup", path="/x/dlp_sample_1.txt"),
            ]
            aud = _auditor(_FakeBackend(evs), tmp=tmp)
            result = aud.finalize_and_write([_rep("c1", sensitive_file="dlp_sample_1.txt")])
            self.assertEqual(result.total, 1)
            self.assertEqual(result.expected, 1)


class InconclusiveTests(unittest.TestCase):
    def test_collect_error_is_inconclusive_and_still_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            aud = _auditor(_RaisingBackend(), tmp=tmp)
            result = aud.finalize_and_write([_rep("c1", sensitive_file="a.txt")])
            self.assertEqual(result.status, "inconclusive")
            self.assertIn("解密失败", result.reason)
            self.assertTrue(Path(result.audit_json_path).exists())

    def test_unexpected_backend_error_degrades_to_inconclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            aud = _auditor(_ExplodingBackend(), tmp=tmp)
            result = aud.finalize_and_write([_rep("c1")])
            self.assertEqual(result.status, "inconclusive")
            self.assertIn("炸了", result.reason)

    def test_backend_without_collect_events_is_inconclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            aud = _auditor(_NoCollectBackend(), tmp=tmp)
            result = aud.finalize_and_write([_rep("c1")])
            self.assertEqual(result.status, "inconclusive")
            self.assertIn("collect_events", result.reason)

    def test_inconclusive_summary_line_never_claims_clean(self):
        r = AuditResult(status="inconclusive", reason="解密失败")
        line = r.summary_line()
        self.assertIn("未完成", line)
        self.assertNotIn("无疑似误报", line)


class ProductTests(unittest.TestCase):
    def test_csv_only_contains_suspicious_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            evs = [
                _event(uuid="u1", path="/x/dlp_sample_1.txt"),         # expected
                _event(uuid="u2", path="/x/stranger.docx"),           # unexpected
            ]
            aud = _auditor(_FakeBackend(evs), tmp=tmp)
            result = aud.finalize_and_write([_rep("c1", sensitive_file="dlp_sample_1.txt")])

            with open(result.unexpected_csv_path, encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f))
            # 表头 + 只有 1 条疑似（unexpected），expected 不进 CSV
            self.assertEqual(len(rows), 2)
            self.assertIn("stranger.docx", rows[1][3])

    def test_audit_json_holds_full_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev = _event(uuid="u1", path="/x/dlp_sample_1.txt")
            aud = _auditor(_FakeBackend([ev]), tmp=tmp)
            aud.record_expectation(
                case_id="c1", kind="file", sensitive_file="dlp_sample_1.txt",
                started_at=_BASE, finished_at=_BASE + timedelta(seconds=5))
            result = aud.finalize_and_write([_rep("c1", sensitive_file="dlp_sample_1.txt")])

            data = json.loads(Path(result.audit_json_path).read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "completed")
            self.assertEqual(data["summary"]["expected"], 1)
            self.assertEqual(len(data["events"]), 1)
            self.assertEqual(len(data["expectations"]), 1)
            self.assertIn("run_started_at", data["timeline"])


# ── runner 集成：顺序（硬约束 1）、零回归、崩溃隔离 ──────────────────────
def _context(root):
    root = Path(root)
    return RunContext(
        run_id=RunContext.new_run_id(),
        platform=CURRENT,
        settings=Settings(),
        report_dir=root / "reports",
        log_dir=root / "logs",
        screenshot_root=root / "screenshots" / "final",
    )


class _OrderWriter:
    def __init__(self, log):
        self.log = log

    def open_incremental(self, _run_id):
        self.log.append("open_incremental")
        return "path"

    def append_case(self, _rep):
        self.log.append("append_case")

    def close_incremental(self):
        self.log.append("close_incremental")

    def write(self, _report):
        self.log.append("write")


class _OrderAuditor:
    def __init__(self, log):
        self.log = log

    def mark_run_started(self):
        self.log.append("run_started")

    def mark_actions_finished(self):
        self.log.append("actions_finished")

    def finalize_and_write(self, _reps):
        self.log.append("finalize")
        return SimpleNamespace(summary_line=lambda: "audit summary")


class _RecordingAuditor:
    def __init__(self):
        self.expectations = []
        self.run_started = False
        self.actions_finished = False

    def mark_run_started(self):
        self.run_started = True

    def mark_actions_finished(self):
        self.actions_finished = True

    def record_expectation(self, **kwargs):
        self.expectations.append(kwargs)

    def finalize_and_write(self, _reps):
        return SimpleNamespace(summary_line=lambda: "x")


class _RaisingAuditor:
    def mark_run_started(self):
        pass

    def mark_actions_finished(self):
        pass

    def finalize_and_write(self, _reps):
        raise RuntimeError("审计器崩了")


def _noop_case():
    return CaseSpec(id="c.noop", name="noop", channel="desktop_app.im",
                    platforms=[CURRENT], define=lambda: [])


class RunnerIntegrationTests(unittest.TestCase):
    def test_audit_runs_after_report_persist(self):
        with tempfile.TemporaryDirectory() as tmp:
            log: list[str] = []
            runner = CaseRunner(context=_context(tmp),
                                writer=_OrderWriter(log),
                                auditor=_OrderAuditor(log))
            runner.run([_noop_case()])
            # 硬约束 1：finalize 必须排在主报告持久化（close_incremental）之后。
            self.assertLess(log.index("close_incremental"), log.index("finalize"))
            self.assertLess(log.index("run_started"), log.index("finalize"))
            self.assertLess(log.index("actions_finished"), log.index("finalize"))

    def test_expect_dlp_step_registers_expectation_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            aud = _RecordingAuditor()

            def _define():
                def _send(ctx):
                    ctx.extras["sensitive_file"] = "unique_x.txt"
                return [expect_dlp(step("send", hard(_send)), "file")]

            case = CaseSpec(id="c.file", name="file", channel="desktop_app.im",
                            platforms=[CURRENT], define=_define)
            CaseRunner(context=_context(tmp), auditor=aud).run([case])

            self.assertTrue(aud.run_started and aud.actions_finished)
            self.assertEqual(len(aud.expectations), 1)
            self.assertEqual(aud.expectations[0]["kind"], "file")
            self.assertEqual(aud.expectations[0]["case_id"], "c.file")
            self.assertEqual(aud.expectations[0]["sensitive_file"], "unique_x.txt")

    def test_auditor_none_does_not_touch_case_report(self):
        # 零回归：auditor=None 时，即便 step 带 dlp_expectation，也不登记、不改结论。
        with tempfile.TemporaryDirectory() as tmp:
            def _define():
                return [expect_dlp(step("send", hard(lambda ctx: None)), "file")]

            case = CaseSpec(id="c.inert", name="inert", channel="desktop_app.im",
                            platforms=[CURRENT], define=_define)
            rep = CaseRunner(context=_context(tmp), auditor=None).run_one(case)
            # 未启用额外验收 → 仍是 inconclusive（与不引入本能力完全一致）。
            self.assertEqual(rep.execution_status, "passed")
            self.assertEqual(rep.status, "inconclusive")

    def test_audit_crash_does_not_break_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = CaseRunner(context=_context(tmp), auditor=_RaisingAuditor())
            report = runner.run([_noop_case()])
            self.assertEqual(report.total, 1)
            self.assertEqual(report.inconclusive, 1)


class ExpectDlpAnnotationTests(unittest.TestCase):
    def test_expect_dlp_sets_field_and_returns_same_step(self):
        s = step("send", hard(lambda ctx: None))
        returned = expect_dlp(s, "image")
        self.assertIs(returned, s)
        self.assertIsNotNone(s.dlp_expectation)
        self.assertEqual(s.dlp_expectation.kind, "image")

    def test_expect_dlp_none_passthrough(self):
        self.assertIsNone(expect_dlp(None, "file"))

    def test_unannotated_step_has_no_expectation(self):
        s = step("plain", hard(lambda ctx: None))
        self.assertIsNone(s.dlp_expectation)


if __name__ == "__main__":
    unittest.main()
