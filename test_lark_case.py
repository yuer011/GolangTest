"""Lark Windows IM case 与国内飞书进程隔离的回归测试。"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from dlp_auto.actions._windows import apps as windows_apps
from dlp_auto.actions._windows import tray as windows_tray
from dlp_auto.case import im_windows_common as common
from dlp_auto.case.contacts import outbound_target


_ROOT = Path(__file__).resolve().parents[1]
_CASE_PATH = (
    _ROOT / "cases" / "desktop_app" / "im" / "windows" / "case_lark.py"
)


def _load_case_module():
    spec = importlib.util.spec_from_file_location("test_case_lark_module", _CASE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LarkCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load_case_module()
        cls.cases = [
            cls.module.case_drag_drop,
            cls.module.case_upload,
            cls.module.case_copy_paste,
            cls.module.case_screenshot,
        ]

    @staticmethod
    def _steps(case):
        return [item for item in case.define() if item is not None]

    def test_registers_four_windows_im_cases(self):
        self.assertEqual(
            [case.id for case in self.cases],
            [
                "desktop_app.im.lark.outbound_file.drag_drop",
                "desktop_app.im.lark.outbound_file.upload",
                "desktop_app.im.lark.outbound_file.copy_paste",
                "desktop_app.im.lark.outbound_screenshot.builtin_capture",
            ],
        )
        for case in self.cases:
            with self.subTest(case=case.id):
                self.assertEqual(case.channel, "desktop_app.im")
                self.assertEqual(case.app, "Lark")
                self.assertEqual([p.value for p in case.platforms], ["windows"])
                self.assertTrue(case.reflect)

    def test_targets_configurable_dlp_test_group(self):
        app = self.module._APP
        self.assertEqual(app.contacts_app, "lark")
        self.assertEqual(app.target_kind, "群聊")
        self.assertEqual(
            app.target,
            outbound_target("desktop_app.im", "lark", default="DLP测试"),
        )
        with (_ROOT / "config" / "contacts.example.yaml").open(
            "r", encoding="utf-8",
        ) as fp:
            contacts = yaml.safe_load(fp)
        self.assertEqual(
            contacts["outbound_targets"]["desktop_app.im"]["lark"]["default"],
            "DLP测试",
        )
        for case in self.cases:
            with self.subTest(case=case.id):
                enter = next(
                    step for step in self._steps(case)
                    if step.name.startswith("搜索并进入")
                )
                self.assertIn(app.target, enter.name)
                self.assertIn("群聊", enter.payload)

    def test_lark_and_feishu_have_strictly_separate_process_identity(self):
        self.assertEqual(windows_apps._exe_names("lark"), ["lark.exe"])
        self.assertEqual(windows_apps._exe_names("feishu"), ["feishu.exe"])
        self.assertEqual(windows_apps._title_hints("lark"), ["lark"])
        self.assertNotIn("lark", windows_apps._title_hints("feishu"))
        self.assertNotIn("feishu", windows_apps._title_hints("lark"))
        self.assertEqual(windows_tray._tray_hints("lark"), ["lark"])
        self.assertNotIn("lark", windows_tray._tray_hints("feishu"))

    def test_lark_uses_verified_executable_path_without_feishu_fallback(self):
        candidates = windows_apps._EXE_CANDIDATES["lark"]
        self.assertEqual(candidates[0], r"C:\Program Files\Lark\app\Lark.exe")
        self.assertFalse(any("Feishu" in path for path in candidates))

    def test_open_uses_lark_and_exact_tray_wake(self):
        app = self.module._APP
        self.assertTrue(app.open_wake_tray)
        ctx = SimpleNamespace(settings=None)
        with (
            patch.object(common.apps, "open_app") as open_app,
            patch.object(common.apps, "ensure_foreground", return_value=True),
            patch.object(common.time, "sleep"),
        ):
            common._make_open_app(app)(ctx)
        open_app.assert_called_once_with(
            "lark",
            wait_sec=app.open_wait_sec,
            wake_tray=True,
            tray_hints=None,
        )

    def test_teardown_only_closes_lark_window(self):
        app = self.module._APP
        with patch.object(common.apps, "close_windows", return_value=1) as close:
            common.make_app_teardown(app)()
        close.assert_called_once_with(["lark"], exe_names=["lark.exe"])

    def test_four_flows_use_shared_factories_with_manual_send_defaults(self):
        expectations = {
            self.module.case_drag_drop.id: "从资源管理器拖拽一个文件到 Lark 对话框发送",
            self.module.case_upload.id: "在 Lark 里确认发送该文件",
            self.module.case_copy_paste.id: "在 Lark 输入框粘贴并发送该文件",
            self.module.case_screenshot.id: "用 Lark 自带截图功能截图并发送",
        }
        for case in self.cases:
            with self.subTest(case=case.id):
                names = [step.name for step in self._steps(case)]
                self.assertIn(expectations[case.id], names)

    def test_manual_file_send_rejects_historical_matching_file(self):
        for case in (
            self.module.case_drag_drop,
            self.module.case_upload,
            self.module.case_copy_paste,
        ):
            with self.subTest(case=case.id):
                sent = next(
                    step for step in reversed(self._steps(case))
                    if step.verify and "文件名形如" in step.verify
                )
                self.assertIn("before 中没有、after 中新出现", sent.verify)
                self.assertIn("历史 dlp_sample_* 文件不通过", sent.verify)


if __name__ == "__main__":
    unittest.main()
