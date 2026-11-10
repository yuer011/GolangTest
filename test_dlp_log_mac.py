"""MacCorplinkBackend 单元测试。

用注入 bread 明文输出的方式验证事件解析、时间窗、文件/截图匹配
和报告回填，
不依赖 sudo 或真机日志。另单独验证最小权限命令形状为
``sudo -n cat <日志路径> | <bread绝对路径> -``。
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from dlp_auto.report.schema import CaseReport
from dlp_auto.verify.dlp_log._mac import (
    _BREAD_FORMAT,
    MacCorplinkBackend,
    parse_mac_event_line,
    parse_mac_line_ts,
)
from dlp_auto.verify.outcome import CheckContext

_CATEGORY = "EDLP:DLP"
_MARKER = "dlp audit event:"


def _event_line(
    *,
    event_id: str = "A1F15FD2-BD36-4835-BFB2-70408A19D75D",
    app_name: str = "feishu",
    file_path: str = "/Users/bytedance/Downloads/测试计划.jmx",
    file_name: str = "测试计划.jmx",
    extension: str = ".jmx",
    timestamp: str = "2026-08-08 17:34:23.729526000",
) -> str:
    payload = {
        "eventId": event_id,
        "configDesc": json.dumps(
            {
                "cfgName": "c53d7651-b689-4030-b636-d31d314d42ab",
                "cfgVersion": "1786180364",
            }
        ),
        "timestamp": "1786181663",
        "sensitiveLevel": {"level": 1, "name": "L1"},
        "matchedKey": "2",
        "tagVersion": "24011100",
        "leakType": "DLP_SOURCE_TYPE_SOFTWARE_READ",
        "appLeak": {
            "appName": app_name,
            "appEnvInfo": {"tenantId": "1"},
            "imInfo": {
                "receiverName": "测试",
                "receiverType": "DLP_RECEIVER_TYPE_GROUP",
            },
        },
        "leakTargetTag": "file:builtin:any_file",
        "targetFile": {
            "leakFilePath": file_path,
            "leakFileName": file_name,
            "leakFileExtension": extension,
            "leakFileContentType": "application/octet-stream",
        },
        "leakFileActions": "4",
    }
    return (
        f"{timestamp}\t[{_CATEGORY}]\t{_MARKER} "
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


class _FakeDecodeBackend(MacCorplinkBackend):
    def __init__(self, plaintext: str, **kwargs):
        root = Path(__file__).resolve().parents[1]
        kwargs.setdefault("path", str(Path(__file__)))
        kwargs.setdefault("decoder", str(root / "bread"))
        kwargs.setdefault("event_category", _CATEGORY)
        kwargs.setdefault("event_marker", _MARKER)
        kwargs.setdefault(
            "image_exts", [".png", ".jpg", ".jpeg", ".bmp", ".gif"]
        )
        kwargs.setdefault("use_sudo", True)
        kwargs.setdefault("settle_wait_sec", 0)
        super().__init__(**kwargs)
        self._plaintext = plaintext

    def _decode_text(self):
        return self._plaintext


def _ctx(
    sensitive_file: str, window_start: datetime | None = None
) -> CheckContext:
    rep = CaseReport(
        id="t",
        name="n",
        channel="desktop_app.im",
        platform="mac",
        sensitive_file=sensitive_file,
    )
    ctx = CheckContext(case=SimpleNamespace(id="t"), rep=rep)
    ctx.policy = "audit"
    ctx.extras["dlp_log_window_start"] = (
        window_start or datetime(2026, 8, 8, 17, 0, 0)
    )
    return ctx


class MacEventParseTests(unittest.TestCase):
    def test_nanosecond_timestamp_is_parsed_to_microseconds(self):
        parsed = parse_mac_line_ts(_event_line())
        self.assertEqual(parsed, datetime(2026, 8, 8, 17, 34, 23, 729526))

    def test_real_event_json_fields_are_parsed(self):
        event = parse_mac_event_line(_event_line(), _CATEGORY, _MARKER)
        self.assertIsNotNone(event)
        self.assertEqual(
            event.event_uuid, "A1F15FD2-BD36-4835-BFB2-70408A19D75D"
        )
        self.assertEqual(event.process_name, "feishu")
        self.assertEqual(
            event.origin_file_path,
            "/Users/bytedance/Downloads/测试计划.jmx",
        )
        self.assertEqual(event.extras["leak_file_extension"], ".jmx")
        self.assertEqual(event.tag_name, "file:builtin:any_file")

    def test_invalid_json_or_event_id_is_not_an_event(self):
        malformed = (
            "2026-08-08 17:34:23.729526000"
            f"\t[{_CATEGORY}]\t{_MARKER} not-json"
        )
        self.assertIsNone(
            parse_mac_event_line(malformed, _CATEGORY, _MARKER)
        )
        self.assertIsNone(
            parse_mac_event_line(
                _event_line(event_id="not-a-uuid"),
                _CATEGORY,
                _MARKER,
            )
        )


class MacBackendMatchTests(unittest.TestCase):
    def test_file_case_matches_name_and_fills_report(self):
        backend = _FakeDecodeBackend(_event_line() + "\n")
        ctx = _ctx("测试计划.jmx")

        outcome = backend.check(ctx)

        self.assertEqual(outcome.status, "passed")
        self.assertEqual(ctx.rep.dlp_process_name, "feishu")
        self.assertEqual(
            ctx.rep.event_id, "A1F15FD2-BD36-4835-BFB2-70408A19D75D"
        )
        self.assertIn(_MARKER, ctx.rep.dlp_event_log)
        self.assertEqual(
            outcome.evidence["origin_file_path"],
            "/Users/bytedance/Downloads/测试计划.jmx",
        )

    def test_screenshot_case_matches_image_extension(self):
        line = _event_line(
            event_id="DD5AD17E-A737-4119-B699-FF821F669B65",
            file_path="screenshot.jpeg",
            file_name="screenshot.jpeg",
            extension=".jpeg",
        )
        backend = _FakeDecodeBackend(line + "\n")
        ctx = _ctx("")

        outcome = backend.check(ctx)

        self.assertEqual(outcome.status, "passed")
        self.assertEqual(outcome.evidence["leak_file_extension"], ".jpeg")
        self.assertEqual(ctx.rep.event_id, "DD5AD17E-A737-4119-B699-FF821F669B65")

    def test_block_hit_backfills_event_id_but_stays_inconclusive(self):
        backend = _FakeDecodeBackend(_event_line() + "\n")
        ctx = _ctx("测试计划.jmx")
        ctx.policy = "block"

        outcome = backend.check(ctx)

        self.assertEqual(outcome.status, "inconclusive")
        self.assertIn("阻断语义尚未标定", outcome.detail)
        self.assertEqual(
            ctx.rep.event_id,
            "A1F15FD2-BD36-4835-BFB2-70408A19D75D",
        )

    def test_block_no_match_is_inconclusive(self):
        backend = _FakeDecodeBackend("")
        ctx = _ctx("测试计划.jmx")
        ctx.policy = "block"

        outcome = backend.check(ctx)

        self.assertEqual(outcome.status, "inconclusive")
        self.assertIn("缺少阻断铁证", outcome.detail)

    def test_event_before_window_is_ignored(self):
        backend = _FakeDecodeBackend(_event_line() + "\n")
        ctx = _ctx(
            "测试计划.jmx",
            window_start=datetime(2026, 8, 8, 18, 0, 0),
        )

        outcome = backend.check(ctx)

        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.evidence["events_in_window"], 0)

    def test_marker_text_without_valid_event_is_not_counted(self):
        plaintext = (
            "2026-08-08 17:34:23.729526000"
            "\t[EDLP:ScreenTime]\tshell echo: "
            f"{_event_line()}\n"
        )
        backend = _FakeDecodeBackend(plaintext)
        outcome = backend.check(_ctx("测试计划.jmx"))
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.evidence["events_in_window"], 0)


class MacBackendDecodeTests(unittest.TestCase):
    def _backend(self, *, use_sudo=True):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        log_path = root / "edlp.log"
        decoder = root / "bread"
        log_path.write_bytes(b"encrypted")
        decoder.write_bytes(b"fake")
        decoder.chmod(0o700)
        backend = MacCorplinkBackend(
            path=str(log_path),
            decoder=str(decoder),
            event_category=_CATEGORY,
            event_marker=_MARKER,
            image_exts=[".jpeg"],
            use_sudo=use_sudo,
            settle_wait_sec=0,
        )
        return backend, log_path, decoder

    @patch("dlp_auto.verify.dlp_log._mac.shutil.which")
    @patch("dlp_auto.verify.dlp_log._mac.subprocess.run")
    def test_decoder_uses_noninteractive_sudo(
        self, run_mock, which_mock
    ):
        backend, log_path, decoder = self._backend()
        which_mock.side_effect = ["/usr/bin/sudo", "/bin/cat"]
        run_mock.side_effect = [
            SimpleNamespace(
                returncode=0,
                stdout=b"encrypted",
                stderr=b"",
            ),
            SimpleNamespace(
                returncode=0,
                stdout=b"decoded",
                stderr=b"",
            ),
        ]

        self.assertEqual(backend._decode_text(), "decoded")

        read_call, decode_call = run_mock.call_args_list
        self.assertEqual(
            read_call.args[0],
            [
                "/usr/bin/sudo",
                "-n",
                "/bin/cat",
                str(log_path),
            ],
        )
        self.assertEqual(
            decode_call.args[0],
            [
                str(decoder.resolve()),
                "-f",
                _BREAD_FORMAT,
                "-",
            ],
        )
        self.assertEqual(
            decode_call.kwargs["input"],
            b"encrypted",
        )
        self.assertTrue(decode_call.kwargs["capture_output"])

    @patch("dlp_auto.verify.dlp_log._mac.shutil.which")
    @patch("dlp_auto.verify.dlp_log._mac.subprocess.run")
    def test_sudo_not_pre_authorized_is_inconclusive(
        self, run_mock, which_mock
    ):
        backend, _, _ = self._backend()
        which_mock.side_effect = ["/usr/bin/sudo", "/bin/cat"]
        run_mock.return_value = SimpleNamespace(
            returncode=1,
            stdout=b"",
            stderr=b"sudo: a password is required",
        )

        outcome = backend.check(_ctx("测试计划.jmx"))

        self.assertEqual(outcome.status, "inconclusive")
        self.assertIn("sudo -v", outcome.detail)

    def test_missing_config_is_inconclusive(self):
        backend = MacCorplinkBackend(
            path=None,
            decoder=None,
            event_category=None,
            event_marker=None,
            image_exts=None,
            settle_wait_sec=0,
        )
        outcome = backend.check(_ctx(""))
        self.assertEqual(outcome.status, "inconclusive")
        self.assertIn("路径", outcome.detail)

    @patch("dlp_auto.verify.dlp_log._mac.subprocess.run")
    def test_timeout_is_inconclusive(self, run_mock):
        backend, _, _ = self._backend(use_sudo=False)
        run_mock.side_effect = subprocess.TimeoutExpired(
            cmd=["bread"], timeout=60
        )
        outcome = backend.check(_ctx(""))
        self.assertEqual(outcome.status, "inconclusive")
        self.assertIn("超时", outcome.detail)


if __name__ == "__main__":
    unittest.main()
