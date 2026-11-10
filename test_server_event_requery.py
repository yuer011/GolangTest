"""服务端事件回查（run 级 + event_id 精确匹配，CHG-004）的单元测试。

覆盖：
- ServerEventChecker.check_run 的 mock / 无 event_id / 命中 / 未命中 / 全局只等一次；
- VerificationManager.on_run_finished 回填并重聚合；
- build_manager 的策略门控（policy=none 不挂 run_checker，零回归）；
- feilian_client 的密码加密确定性与响应解析（不触网）；
- ReportWriter 新增「事件ID」列落盘。
"""
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from dlp_auto.config import Settings
from dlp_auto.report.schema import CaseReport, RunReport
from dlp_auto.report.writer import ReportWriter, _CSV_HEADER
from dlp_auto.verify import build_manager
from dlp_auto.verify.manager import VerificationManager
from dlp_auto.verify.server_event import ServerEventChecker


def _rep(case_id: str, event_id: str = "") -> CaseReport:
    rep = CaseReport(id=case_id, name=case_id, channel="im", platform="windows")
    rep.execution_status = "passed"
    rep.event_id = event_id
    return rep


def _run(*cases: CaseReport) -> RunReport:
    return RunReport(
        run_id="r-test",
        started_at="2026-08-06T10:00:00",
        finished_at="2026-08-06T10:05:00",
        cases=list(cases),
    )


class CheckRunTests(unittest.TestCase):
    def test_no_event_id_is_inconclusive(self):
        chk = ServerEventChecker(mock=True)
        out = chk.check_run(_run(_rep("c1")))  # 无 event_id
        self.assertEqual(out["c1"].status, "inconclusive")
        self.assertIn("未取得事件ID", out["c1"].detail)

    def test_mock_always_inconclusive_even_with_event_id(self):
        chk = ServerEventChecker(mock=True)
        out = chk.check_run(_run(_rep("c1", "uuid-1")))
        self.assertEqual(out["c1"].status, "inconclusive")
        self.assertTrue(out["c1"].evidence["mocked"])

    def test_real_hit_passes_and_miss_inconclusive(self):
        # policy=none：命中即过（不做处置校验），未命中 inconclusive。
        chk = ServerEventChecker(mock=False, report_delay_sec=0.0)
        chk._query = lambda ids, start, end: {"uuid-hit": [{"id": "uuid-hit"}]}
        out = chk.check_run(_run(_rep("c1", "uuid-hit"), _rep("c2", "uuid-miss")))
        self.assertEqual(out["c1"].status, "passed")
        self.assertEqual(out["c2"].status, "inconclusive")

    def test_multiple_events_for_one_id_fails(self):
        # event_id 是 UUID 本应唯一；查到 >1 条 → failed（原因落表）。
        chk = ServerEventChecker(mock=False, report_delay_sec=0.0)
        chk._query = lambda ids, start, end: {"u1": [{"id": "a"}, {"id": "b"}]}
        out = chk.check_run(_run(_rep("c1", "u1")))
        self.assertEqual(out["c1"].status, "failed")
        self.assertIn("2 条", out["c1"].detail)
        self.assertEqual(out["c1"].evidence["count"], 2)

    def test_audit_allowed_passes_intercepted_fails(self):
        # audit 应放行：event_result 无 intercept（或非真）=放行=passed；intercept=真=failed。
        chk = ServerEventChecker(mock=False, report_delay_sec=0.0, policy="audit")
        chk._query = lambda ids, start, end: {
            "allow": [{"event_result": {"alert": True, "file_flow": True}}],
            "block": [{"event_result": {"intercept": True}}],
        }
        out = chk.check_run(_run(_rep("c1", "allow"), _rep("c2", "block")))
        self.assertEqual(out["c1"].status, "passed")   # 放行，符合审计
        self.assertEqual(out["c2"].status, "failed")   # 被拦截，与审计不符
        self.assertIn("拦截", out["c2"].detail)

    def test_block_intercepted_passes_allowed_fails(self):
        # block 应拦截：intercept=真=passed；放行（无 intercept）=failed（阻断失效）。
        chk = ServerEventChecker(mock=False, report_delay_sec=0.0, policy="block")
        chk._query = lambda ids, start, end: {
            "block": [{"event_result": {"intercept": True}}],
            "leak": [{"event_result": {"file_flow": True}}],
        }
        out = chk.check_run(_run(_rep("c1", "block"), _rep("c2", "leak")))
        self.assertEqual(out["c1"].status, "passed")   # 已拦截，符合阻断
        self.assertEqual(out["c2"].status, "failed")   # 放行，阻断失效
        self.assertIn("阻断失效", out["c2"].detail)

    def test_intercept_missing_event_result_treated_as_allowed(self):
        # event_result 整个缺失：按放行处理（不臆测、不误报拦截）。audit 下应 passed。
        chk = ServerEventChecker(mock=False, report_delay_sec=0.0, policy="audit")
        chk._query = lambda ids, start, end: {"u1": [{"event_id": "u1"}]}
        out = chk.check_run(_run(_rep("c1", "u1")))
        self.assertEqual(out["c1"].status, "passed")

    def test_global_wait_happens_at_most_once(self):
        # 首轮全 miss → 等一次补查；补查后仍 miss → 记 inconclusive，且只等这一次。
        calls = {"n": 0}

        def fake_query(ids, start, end):
            calls["n"] += 1
            return {}  # 恒查不到

        chk = ServerEventChecker(mock=False, report_delay_sec=0.0)
        chk._query = fake_query
        out = chk.check_run(_run(_rep("c1", "uuid-1")))
        self.assertEqual(out["c1"].status, "inconclusive")
        self.assertTrue(chk._waited)
        self.assertEqual(calls["n"], 2)  # 首查 + 补查一次，不再多等

    def test_second_run_does_not_wait_again(self):
        # _waited 是实例级：同一 checker 复用时，第二次 check_run 不再等待。
        chk = ServerEventChecker(mock=False, report_delay_sec=999.0)
        chk._query = lambda ids, start, end: {}
        chk._waited = True  # 模拟已等过
        # report_delay_sec=999 但因已 waited，不应真的 sleep（测试能秒回即证明）
        out = chk.check_run(_run(_rep("c1", "uuid-1")))
        self.assertEqual(out["c1"].status, "inconclusive")

    def test_query_exception_degrades_to_inconclusive(self):
        chk = ServerEventChecker(mock=False, report_delay_sec=0.0)

        def boom(ids, start, end):
            raise RuntimeError("网络炸了")

        chk._query = boom
        out = chk.check_run(_run(_rep("c1", "uuid-1")))
        self.assertEqual(out["c1"].status, "inconclusive")
        self.assertIn("异常", out["c1"].detail)

    def test_time_window_derived_from_run(self):
        chk = ServerEventChecker(mock=False, query_window_days=1)
        start, end = chk._time_window(_run(_rep("c1", "u")))
        self.assertLess(start, end)
        self.assertIsInstance(start, int)


class ManagerRunHookTests(unittest.TestCase):
    def test_on_run_finished_records_and_reaggregates(self):
        class HitChecker:
            name = "server_event"
            scope = "run"

            def check_run(self, run_report):
                from dlp_auto.verify.outcome import CheckOutcome
                return {rep.id: CheckOutcome("server_event", "passed", "查到")
                        for rep in run_report.cases}

        rep = _rep("c1", "uuid-1")
        # 服务端 checker 只在 audit/block 下挂载；audit 聚合需 delivery=sent（由视觉推断），
        # 故先播下视觉通过，模拟真实执行期已冒泡的视觉结论。
        rep.extras["checks"] = {
            "visual": {"name": "visual", "status": "passed", "detail": ""}
        }
        mgr = VerificationManager(run_checkers=[HitChecker()], policy="audit")
        run = _run(rep)
        mgr.on_run_finished(run)
        # 回填到 checks 列
        self.assertEqual(rep.extras["checks"]["server_event"]["status"], "passed")
        # 重聚合：视觉→delivery=sent + 服务端 passed → 最终 passed
        self.assertEqual(rep.delivery_outcome, "sent")
        self.assertEqual(rep.status, "passed")

    def test_flip_to_passed_clears_stale_issue(self):
        # CHG-004 真机联调暴露的一致性 bug 回归：某 case 首次聚合时 server_event 还是
        # inconclusive，issue 被写成「未形成确定结论」；run 级回查补查命中翻成 passed 后
        # 重新聚合，issue 必须被清空——passed 的 case 绝不能带着「未形成结论」的矛盾描述。
        class LateHitChecker:
            name = "server_event"
            scope = "run"

            def check_run(self, run_report):
                from dlp_auto.verify.outcome import CheckOutcome
                return {rep.id: CheckOutcome("server_event", "passed",
                                             "服务端已查到本次外发事件。")
                        for rep in run_report.cases}

        rep = _rep("c1", "uuid-1")
        # 模拟执行期已冒泡视觉通过 + 首次聚合（server_event 缺失）留下的残旧 issue。
        rep.extras["checks"] = {
            "visual": {"name": "visual", "status": "passed", "detail": ""}
        }
        rep.issue = "DLP 验收未形成确定结论：server_event=missing"
        mgr = VerificationManager(run_checkers=[LateHitChecker()], policy="audit")
        mgr.on_run_finished(_run(rep))
        self.assertEqual(rep.status, "passed")
        self.assertEqual(rep.issue, "")  # 旧 issue 必须被清空，不残留

    def test_run_checker_exception_degrades(self):
        class BoomChecker:
            name = "server_event"
            scope = "run"

            def check_run(self, run_report):
                raise RuntimeError("boom")

        rep = _rep("c1", "uuid-1")
        mgr = VerificationManager(run_checkers=[BoomChecker()], policy="audit")
        mgr.on_run_finished(_run(rep))
        self.assertEqual(rep.extras["checks"]["server_event"]["status"],
                         "inconclusive")

    def test_run_checkers_counted_in_enabled(self):
        class C:
            name = "server_event"
            scope = "run"

            def check_run(self, run_report):
                return {}

        self.assertTrue(VerificationManager(run_checkers=[C()]).enabled)
        self.assertFalse(VerificationManager().enabled)


class BuildManagerGatingTests(unittest.TestCase):
    def test_check_server_under_policy_mounts_run_checker(self):
        s = Settings(raw={})
        mgr = build_manager(s, check_server=True, policy="audit")
        self.assertEqual([c.name for c in mgr.run_checkers], ["server_event"])

    def test_check_server_under_none_is_gated_off(self):
        # policy=none 拿不到 event_id → 即便 --check-server 也不挂（零回归）。
        s = Settings(raw={})
        mgr = build_manager(s, check_server=True, policy="none")
        self.assertEqual(mgr.run_checkers, [])
        self.assertFalse(mgr.enabled)

    def test_no_check_server_no_run_checker(self):
        s = Settings(raw={})
        mgr = build_manager(s, check_server=False, policy="audit")
        self.assertEqual(mgr.run_checkers, [])


class FeilianClientTests(unittest.TestCase):
    def test_password_encryption_is_deterministic_hex(self):
        from dlp_auto.verify.feilian_client import _aes_encrypt_password
        a = _aes_encrypt_password("s3cr3t")
        b = _aes_encrypt_password("s3cr3t")
        self.assertEqual(a, b)
        int(a, 16)  # 必须是合法 hex
        self.assertEqual(len(a) % 32, 0)  # AES 块对齐（每块 16 字节 = 32 hex）

    def test_extract_events_tolerates_shapes(self):
        from dlp_auto.verify.feilian_client import _extract_events
        self.assertEqual(_extract_events([{"id": 1}]), [{"id": 1}])
        self.assertEqual(_extract_events({"data": [{"id": 2}]}), [{"id": 2}])
        self.assertEqual(_extract_events({"data": {"events": [{"id": 3}]}}),
                         [{"id": 3}])
        self.assertEqual(_extract_events({"data": {"list": [{"id": 4}]}}),
                         [{"id": 4}])
        self.assertEqual(_extract_events({"nope": 1}), [])
        self.assertEqual(_extract_events(None), [])

    def test_build_client_missing_credentials_raises(self):
        # 会话凭据与账号密码都缺 → 抛（两种鉴权来源都没有）。
        from dlp_auto.verify.feilian_client import build_client, FeilianAuthError
        s = Settings(raw={"verify": {"server": {"host": "h"}}})  # 缺全部凭据
        with self.assertRaises(FeilianAuthError):
            build_client(s)

    def test_build_client_missing_host_raises(self):
        from dlp_auto.verify.feilian_client import build_client, FeilianAuthError
        s = Settings(raw={"verify": {"server": {
            "admin_user": "u", "admin_pwd": "p"}}})  # 缺 host
        with self.assertRaises(FeilianAuthError):
            build_client(s)

    def test_build_client_accepts_session_only(self):
        # 只配会话凭据（无账号密码）也能建 client（cookie 优先，跳过登录）。
        from dlp_auto.verify.feilian_client import build_client
        s = Settings(raw={"verify": {"server": {
            "host": "h", "session_cookie": "sid=abc", "csrf_token": "tok"}}})
        client = build_client(s)
        self.assertEqual(client._cookie, "sid=abc")
        self.assertEqual(client._csrf, "tok")

    def test_login_skipped_when_session_injected(self):
        # 注入现成会话后 login() 直接跳过：不触网、不需要密码。
        from dlp_auto.verify.feilian_client import FeilianClient
        client = FeilianClient(host="h", session_cookie="sid=abc", csrf_token="tok")
        client.login()  # 不应抛、不应触网
        self.assertEqual(client._cookie, "sid=abc")
        self.assertEqual(client._csrf, "tok")

    def test_login_requires_credentials_when_no_session(self):
        # 既无会话又无账号密码 → login() 抛（不静默、不触网）。
        from dlp_auto.verify.feilian_client import FeilianClient, FeilianAuthError
        client = FeilianClient(host="h")
        with self.assertRaises(FeilianAuthError):
            client.login()


class WriterEventIdColumnTests(unittest.TestCase):
    def test_event_id_column_present_and_written(self):
        self.assertIn("事件ID", _CSV_HEADER)
        rep = _rep("c1", "uuid-xyz")
        rep.app = "feishu"
        with tempfile.TemporaryDirectory() as tmp:
            w = ReportWriter(out_dir=tmp)
            w.open_incremental("run-x")
            w.append_case(rep)
            w.close_incremental()
            with (Path(tmp) / "run-x.csv").open(encoding="utf-8-sig") as f:
                rows = list(csv.reader(f))
        header, data = rows[0], rows[1]
        self.assertEqual(data[header.index("事件ID")], "uuid-xyz")


if __name__ == "__main__":
    unittest.main()
