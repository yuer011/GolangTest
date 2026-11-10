"""WindowsCorplinkBackend 单元测试（DLP 客户端日志验证）。

用「注入明文」的方式（override _decode 返回预置明文文件）验证核心逻辑，
不依赖真实解密器 exe，故可跨平台在 CI 跑。覆盖：
- 行首锚只认真实事件行，排除宿主 shell 回显（ndlp_svc_mgr.cpp on websocket msg，
  其 JSON 里照抄了事件全文）——这是实测踩过的坑，重点回归保护。
- 文件类按唯一文件名匹配 origin file path。
- 截图类（sensitive_file 空）按图片扩展名匹配、进程名不参与。
- 时间窗过滤：窗前的事件不算。
- 缺配置/解密失败降级 inconclusive。
"""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from dlp_auto.report.schema import CaseReport
from dlp_auto.verify.dlp_log._windows import WindowsCorplinkBackend, _DecodeError
from dlp_auto.verify.outcome import CheckContext, CheckOutcome

_TS = "[2026-08-03 19:55:02.251]"
_PID = "[21956:7028] [default] [info]"

# 一条真实事件行（文件外发）
_REAL_FILE = (f"{_TS} {_PID} dlp_event_upload_handler.cpp:2262 事件UUID : "
              "509034d2-79e7-4763-a542-eb218e0fcce6 rule_name: c53d-uuid "
              "tag name is file:builtin:any_file | process name is QQ.exe | "
              r"origin file path is C:\Users\Admin\dlp_sample_ABC123.txt")
# 一条真实事件行（截图外发，文件名未知=screenshot.png）
_REAL_SHOT = (f"{_TS} {_PID} dlp_event_upload_handler.cpp:2262 事件UUID : "
              "6fcf87e2-1f6e-40c0-a25d-919f7ba7c718 rule_name: c53d-uuid "
              "tag name is file:builtin:any_file | process name is Feishu.exe | "
              "origin file path is screenshot.png")
# 宿主 shell 回显行：ndlp_svc_mgr.cpp:643，JSON 里照抄了上面的真实事件全文
_ECHO = (f"{_TS} {_PID} ndlp_svc_mgr.cpp:643 on websocket msg, req: "
         '{"tool_input":{"command":"...' + _REAL_FILE + '..."}}')

# 同一 event_marker（dlp_event_upload_handler.cpp）打的「批量上传」管理型汇总行——
# 真机实测同一 marker 3554 行里仅 1 行是真事件，其余全是这三类：都**既无事件UUID
# 也无 origin file path**，只有 size/batched 等计数，是审计噪声的真实来源。
_NOISE_START = (f"{_TS} {_PID} dlp_event_upload_handler.cpp:1180 "
                "start upload dlp event, size: 5")
_NOISE_BATCH = (f"{_TS} {_PID} dlp_event_upload_handler.cpp:1195 "
                "upload dlp batch, db loaded: 5 batched: 5")
_NOISE_TAG = (f"{_TS} {_PID} dlp_event_upload_handler.cpp:1210 "
              "upload associate tag size: 0")


class _FakeDecodeBackend(WindowsCorplinkBackend):
    """把解密替换成「返回预置明文文件」，其余逻辑走真实实现。

    check() 会先做 path/decoder 存在性校验，故这里把二者都指向真实存在的文件
    （本测试文件自身）以通过前置检查；真正读取的内容由被 override 的 _decode 提供。
    """

    def __init__(self, plaintext: str, **kw):
        real = str(Path(__file__))
        kw.setdefault("path", real)
        kw.setdefault("decoder", real)
        super().__init__(**kw)
        self._plain = plaintext
        self._tmp = Path(tempfile.mkdtemp()) / "plain.log"
        self._tmp.write_text(plaintext, encoding="utf-8")

    def _decode(self, src):  # noqa: D401 - 覆盖真实解密
        return self._tmp

    # 真实实现里 _decode 后会 _cleanup(dst) 删除；这里不希望删掉复用的明文文件
    @staticmethod
    def _cleanup(dst):
        pass


def _ctx(sensitive_file: str, window_start=None) -> CheckContext:
    rep = CaseReport(id="t", name="n", channel="c", platform="windows",
                     sensitive_file=sensitive_file)
    ctx = CheckContext(case=SimpleNamespace(id="t"), rep=rep)
    ctx.extras["dlp_log_window_start"] = window_start or datetime(2026, 8, 3, 0, 0, 0)
    return ctx


class WindowsBackendMatchTests(unittest.TestCase):
    def _run(self, plaintext, sensitive_file, **kw):
        be = _FakeDecodeBackend(plaintext, settle_wait_sec=0, **kw)
        ctx = _ctx(sensitive_file)
        return be.check(ctx), ctx.rep

    def test_file_case_matches_unique_name(self):
        out, rep = self._run(_REAL_FILE + "\n", "dlp_sample_ABC123.txt")
        self.assertEqual(out.status, "passed")
        self.assertEqual(rep.dlp_process_name, "QQ.exe")
        self.assertEqual(out.evidence["origin_file_path"],
                         r"C:\Users\Admin\dlp_sample_ABC123.txt")
        self.assertIn("dlp_event_upload_handler.cpp", rep.dlp_event_log)

    def test_screenshot_case_matches_by_image_ext(self):
        out, rep = self._run(_REAL_SHOT + "\n", "")   # 截图类：sensitive_file 空
        self.assertEqual(out.status, "passed")
        self.assertEqual(rep.dlp_process_name, "Feishu.exe")
        self.assertEqual(out.evidence["origin_file_path"], "screenshot.png")

    def test_echo_line_is_not_treated_as_event(self):
        # 只有宿主回显行（内含事件全文）时，行首锚必须拒绝它 → 判 failed，不误报 passed
        out, rep = self._run(_ECHO + "\n", "dlp_sample_ABC123.txt")
        self.assertEqual(out.status, "failed")
        self.assertEqual(rep.dlp_process_name, "")
        self.assertEqual(rep.dlp_event_log, "")
        self.assertEqual(out.evidence.get("events_in_window"), 0)

    def test_echo_and_real_mixed_picks_real_only(self):
        out, rep = self._run(_ECHO + "\n" + _REAL_FILE + "\n",
                             "dlp_sample_ABC123.txt")
        self.assertEqual(out.status, "passed")
        # origin 必须是干净的路径，不含回显 blob
        self.assertEqual(out.evidence["origin_file_path"],
                         r"C:\Users\Admin\dlp_sample_ABC123.txt")
        # 命中的整条事件日志行必须是真实发射源那条，而非回显行
        self.assertIn("dlp_event_upload_handler.cpp", rep.dlp_event_log)
        self.assertNotIn("ndlp_svc_mgr.cpp", rep.dlp_event_log)

    def test_event_before_window_is_ignored(self):
        be = _FakeDecodeBackend(_REAL_FILE + "\n", settle_wait_sec=0)
        # 窗起点设在事件之后 → 事件在窗外 → failed
        ctx = _ctx("dlp_sample_ABC123.txt",
                   window_start=datetime(2026, 8, 3, 20, 0, 0))
        out = be.check(ctx)
        self.assertEqual(out.status, "failed")

    def test_screenshot_case_ignores_non_image_file_event(self):
        # 截图类：窗内只有普通文件事件（非图片扩展名）→ 文件类型不对应 → failed
        out, rep = self._run(_REAL_FILE + "\n", "")
        self.assertEqual(out.status, "failed")


class WindowsBackendDegradeTests(unittest.TestCase):
    def test_missing_decoder_config_is_inconclusive(self):
        be = WindowsCorplinkBackend(path="some.log", decoder=None)
        out = be.check(_ctx(""))
        self.assertEqual(out.status, "inconclusive")
        self.assertIn("解密器", out.detail)

    def test_missing_path_config_is_inconclusive(self):
        be = WindowsCorplinkBackend(path=None, decoder="d.exe")
        out = be.check(_ctx(""))
        self.assertEqual(out.status, "inconclusive")
        self.assertIn("路径", out.detail)

    def test_decode_failure_is_inconclusive(self):
        class _BoomBackend(WindowsCorplinkBackend):
            def _decode(self, src):
                raise _DecodeError("解密失败（测试）")

        # 需要绕过前置的文件存在性检查：用真实存在的文件（本测试文件自身）
        this = Path(__file__)
        be = _BoomBackend(path=str(this), decoder=str(this), settle_wait_sec=0)
        out = be.check(_ctx(""))
        self.assertEqual(out.status, "inconclusive")
        self.assertIn("解密失败", out.detail)


class WindowsBackendRetryTests(unittest.TestCase):
    """事件落盘延迟：首轮未命中时，应「等待→重查」多轮，命中即早退（LESSONS #15）。"""

    def _backend(self, hit_on_attempt: int, **kw):
        """构造一个第 hit_on_attempt 次 _scan_and_judge 调用才命中的后端。"""
        this = Path(__file__)
        calls = {"n": 0}

        class _DelayedHitBackend(WindowsCorplinkBackend):
            def _scan_and_judge(self, ctx, window_start, sensitive_file):
                calls["n"] += 1
                if calls["n"] >= hit_on_attempt:
                    return CheckOutcome(self.name, "passed", "命中（测试）")
                return CheckOutcome(self.name, "failed", "未命中（测试）")

        be = _DelayedHitBackend(path=str(this), decoder=str(this),
                                settle_wait_sec=0.01, **kw)
        return be, calls

    def test_hits_on_a_later_retry_round(self):
        # 首轮 miss、第 3 次调用才命中；settle_retries=3 足够 → 最终 passed
        be, calls = self._backend(hit_on_attempt=3, settle_retries=3)
        out = be.check(_ctx("dlp_sample_x.txt"))
        self.assertEqual(out.status, "passed")
        self.assertEqual(calls["n"], 3)          # 首轮 + 2 次重试即命中，命中即早退

    def test_gives_up_after_exhausting_retries(self):
        # 一直不命中：首轮 + settle_retries 轮全 miss → 保持 failed，且不无限重试
        be, calls = self._backend(hit_on_attempt=99, settle_retries=2)
        out = be.check(_ctx("dlp_sample_x.txt"))
        self.assertEqual(out.status, "failed")
        self.assertEqual(calls["n"], 3)          # 1 首轮 + 2 重试 = 3 次，到顶即停


class CollectEventsNoiseFilterTests(unittest.TestCase):
    """审计专用 collect_events：过滤同 marker 的批量管理汇总行（无 UUID + 无 path）。

    这是 CHG-020 的真机缺陷：event_marker 行首锚能挡住宿主回显（ndlp_svc_mgr.cpp），
    却挡不住同一个 dlp_event_upload_handler.cpp 打的批量汇总行；这些行会被审计兜底判
    成 unexpected，淹没疑似误报产物。collect_events 须只保留「有 UUID 或有 path」的行。
    """

    _WIN_START = datetime(2026, 8, 3, 0, 0, 0)

    def _collect(self, plaintext, **kw):
        be = _FakeDecodeBackend(plaintext, settle_wait_sec=0, **kw)
        return be.collect_events(self._WIN_START, None)

    def test_noise_summary_lines_are_filtered_out(self):
        # 纯噪声：三类批量汇总行都通过了行首锚，但都无 UUID/path → 应被全部过滤
        plaintext = "\n".join([_NOISE_START, _NOISE_BATCH, _NOISE_TAG]) + "\n"
        events = self._collect(plaintext)
        self.assertEqual(events, [])

    def test_real_events_survive_filter(self):
        # 真事件（有 UUID + path）必须保留
        events = self._collect(_REAL_FILE + "\n" + _REAL_SHOT + "\n")
        self.assertEqual(len(events), 2)

    def test_mixed_keeps_only_real_events(self):
        # 混合：1 真事件 + 3 噪声 → 只剩真事件那条
        plaintext = "\n".join(
            [_NOISE_START, _REAL_FILE, _NOISE_BATCH, _NOISE_TAG]) + "\n"
        events = self._collect(plaintext)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_uuid,
                         "509034d2-79e7-4763-a542-eb218e0fcce6")

    def test_echo_line_never_reaches_collect(self):
        # 宿主回显行被行首锚在更早处排除，不因过滤逻辑而漏进来
        events = self._collect(_ECHO + "\n" + _REAL_FILE + "\n")
        self.assertEqual(len(events), 1)
        self.assertNotIn("ndlp_svc_mgr.cpp", events[0].raw_line)

    def test_case_check_unaffected_by_noise_lines(self):
        # 回归护栏：case 级 check() 不走 collect_events；面对同样的「噪声+真事件」，
        # 结论仍由 _match(origin_file_path) 决定，噪声本就不影响它。
        be = _FakeDecodeBackend(
            "\n".join([_NOISE_START, _REAL_FILE, _NOISE_BATCH]) + "\n",
            settle_wait_sec=0)
        out = be.check(_ctx("dlp_sample_ABC123.txt"))
        self.assertEqual(out.status, "passed")
        self.assertEqual(out.evidence["origin_file_path"],
                         r"C:\Users\Admin\dlp_sample_ABC123.txt")


if __name__ == "__main__":
    unittest.main()
