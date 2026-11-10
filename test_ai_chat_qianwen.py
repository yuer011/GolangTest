"""千问 AI应用通道的纯逻辑回归测试（不启动 GUI）。"""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from dlp_auto.actions._windows import apps as windows_apps
from dlp_auto.case import ai_chat_windows_common as common


def _load_case_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "cases"
        / "desktop_app"
        / "ai_chat"
        / "windows"
        / "case_qianwen.py"
    )
    spec = importlib.util.spec_from_file_location(
        "test_case_qianwen_module", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载千问 case：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QianwenCaseFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load_case_module()
        cls.cases = (
            cls.module.case_drag_document,
            cls.module.case_upload_document,
            cls.module.case_upload_image,
            cls.module.case_copy_paste_document,
            cls.module.case_screenshot,
        )

    @staticmethod
    def _steps(case):
        return [item for item in case.define() if item is not None]

    def test_five_cases_use_dedicated_ai_chat_channel(self):
        self.assertEqual(len(self.cases), 5)
        for case in self.cases:
            with self.subTest(case=case.id):
                self.assertEqual(case.channel, "desktop_app.ai_chat")
                self.assertTrue(case.id.startswith("desktop_app.ai_chat.qianwen."))
                self.assertEqual(case.app, "千问")

    def test_qianwen_app_registration_uses_portable_localappdata_path(self):
        candidate = windows_apps._EXE_CANDIDATES["qianwen"][0]
        self.assertIn("%LOCALAPPDATA%", candidate)
        self.assertEqual(windows_apps._title_hints("qianwen"), ["千问", "qianwen"])
        self.assertEqual(windows_apps._exe_names("qianwen"), ["qianwen.exe"])
        self.assertEqual(windows_apps._normalize_app_key("千问"), "qianwen")

        resolved = r"C:\Users\test\AppData\Local\Programs\QianwenApp\qianwen.exe"
        with (
            patch.object(
                windows_apps.os.path,
                "expandvars",
                side_effect=lambda value: resolved if value == candidate else value,
            ),
            patch.object(
                windows_apps.os.path,
                "exists",
                side_effect=lambda value: value == resolved,
            ),
        ):
            self.assertEqual(windows_apps._resolve_exe("qianwen"), resolved)

    def test_conversation_rule_uses_first_existing_or_current(self):
        for case in self.cases:
            with self.subTest(case=case.id):
                enter = next(
                    item for item in self._steps(case)
                    if item.name.startswith("进入 千问 左侧第一个已有对话")
                )
                self.assertEqual(enter.kind, "ai")
                self.assertIn("最上面的第一条对话", enter.payload)
                self.assertIn("左侧没有任何历史对话", enter.payload)
                self.assertIn("沿用当前", enter.payload)
                self.assertIn("不要点击“新对话”", enter.payload)
                self.assertEqual(enter.action_limits, {"click": 2})

    def test_qianwen_relaunches_hidden_single_instance_window(self):
        self.assertTrue(self.module._APP.relaunch_if_hidden)
        ctx = SimpleNamespace(settings=None)
        with (
            patch.object(common.apps, "open_app") as open_app,
            patch.object(common.apps, "ensure_foreground"),
            patch.object(common.time, "sleep"),
        ):
            common._open_app_fn(self.module._APP)(ctx)

        open_app.assert_called_once_with(
            "qianwen",
            wait_sec=self.module._APP.open_wait_sec,
            relaunch_if_hidden=True,
        )

    def test_qianwen_requires_daily_mode_before_conversation(self):
        self.assertEqual(self.module._APP.required_mode, "日常模式")
        for case in self.cases:
            with self.subTest(case=case.id):
                steps = self._steps(case)
                mode_index = next(
                    i for i, item in enumerate(steps)
                    if item.name == "确认 千问 处于日常模式"
                )
                enter_index = next(
                    i for i, item in enumerate(steps)
                    if item.name.startswith("进入 千问 左侧第一个已有对话")
                )
                mode = steps[mode_index]
                self.assertLess(mode_index, enter_index)
                self.assertIn("办公模式", mode.payload)
                self.assertIn("日常模式", mode.payload)
                self.assertEqual(mode.action_limits, {"click": 2})

    def test_file_is_generated_before_entering_conversation(self):
        for case in self.cases[:4]:
            with self.subTest(case=case.id):
                steps = self._steps(case)
                make_index = next(
                    i for i, item in enumerate(steps)
                    if item.name.startswith("生成本次唯一外发")
                )
                enter_index = next(
                    i for i, item in enumerate(steps)
                    if item.name.startswith("进入 千问 左侧第一个已有对话")
                )
                self.assertLess(make_index, enter_index)

    def test_composer_preflight_is_read_only_and_precedes_new_notice(self):
        for case in self.cases:
            with self.subTest(case=case.id):
                steps = self._steps(case)
                check_index = next(
                    i for i, item in enumerate(steps)
                    if item.name.startswith("确认 千问 输入区为空")
                )
                notice_index = next(
                    i for i, item in enumerate(steps)
                    if item.name == "先在千问输入区写入测试声明（暂不发送）"
                )
                check = steps[check_index]
                self.assertLess(check_index, notice_index)
                self.assertIn("只要存在任何草稿内容", check.payload)
                self.assertIn("绝对不要点击、按键、清空", check.payload)
                self.assertEqual(check.action_limits, {})

    def test_notice_precedes_attachment_and_each_flow_sends_once(self):
        attachment_prefixes = (
            "拖拽本次唯一文档",
            "打开千问附件菜单并选择“上传文档”",
            "打开千问附件菜单并选择“上传图片”",
            "把唯一文档粘贴进千问输入区",
            "使用千问“截屏提问”",
        )
        for case, prefix in zip(self.cases, attachment_prefixes):
            with self.subTest(case=case.id):
                steps = self._steps(case)
                notice_index = next(
                    i for i, item in enumerate(steps)
                    if item.name == "先在千问输入区写入测试声明（暂不发送）"
                )
                attachment_index = next(
                    i for i, item in enumerate(steps)
                    if item.name.startswith(prefix)
                )
                sends = [
                    (i, item) for i, item in enumerate(steps)
                    if (
                        item.name.startswith("确定性回车发送")
                        or item.name.startswith("点击千问发送按钮")
                    )
                ]
                self.assertLess(notice_index, attachment_index)
                self.assertEqual(len(sends), 1)
                self.assertGreater(sends[0][0], attachment_index)

    def test_upload_document_and_image_use_distinct_menu_items(self):
        document_step = next(
            item for item in self._steps(self.module.case_upload_document)
            if item.name.startswith("打开千问附件菜单")
        )
        image_step = next(
            item for item in self._steps(self.module.case_upload_image)
            if item.name.startswith("打开千问附件菜单")
        )
        self.assertIn("上传文档", document_step.payload)
        self.assertNotIn("上传图片", document_step.payload)
        self.assertIn("上传图片", image_step.payload)
        self.assertNotIn("上传文档", image_step.payload)
        self.assertEqual(document_step.action_limits, {"click": 2})
        self.assertEqual(image_step.action_limits, {"click": 2})

        image_wait = next(
            item for item in self._steps(self.module.case_upload_image)
            if item.name == "等待千问图片附件加载完成"
        )
        self.assertEqual(image_wait.kind, "hard")

        image_steps = self._steps(self.module.case_upload_image)
        image_send = next(
            item for item in image_steps
            if item.name.startswith("点击千问发送按钮")
        )
        self.assertEqual(image_send.kind, "ai")
        self.assertEqual(image_send.verify_mode, "change")
        self.assertEqual(image_send.action_limits, {"click": 1})
        self.assertIn("只点击输入区右侧/右下角", image_send.payload)
        self.assertIn("紧邻一条我方图片气泡", image_send.verify)

    def test_post_send_observer_requires_empty_composer_and_new_reply(self):
        document_cases = (
            self.module.case_drag_document,
            self.module.case_upload_document,
            self.module.case_copy_paste_document,
        )
        for case in document_cases:
            with self.subTest(case=case.id):
                steps = self._steps(case)
                send_index = next(
                    i for i, item in enumerate(steps)
                    if item.name.startswith("确定性回车发送")
                )
                observer = steps[send_index + 1]
                self.assertEqual(observer.kind, "ai")
                self.assertEqual(observer.verify_mode, "presence")
                self.assertFalse(observer.retry_on_verify_fail)
                self.assertIn(common._TEST_NOTICE, observer.payload)
                self.assertIn("底部输入框完全清空", observer.payload)
                self.assertIn("新的 千问 AI 回复", observer.payload)
                self.assertIn("AI 回复不能代替", observer.payload)
                self.assertIn("绝对不要点击", observer.payload)
                self.assertIn("底部输入框已完全清空", observer.verify)
                self.assertIn("新的 千问 AI 回复", observer.verify)
                self.assertIn("AI 回复也不能替代", observer.verify)

    def test_image_and_screenshot_use_single_ai_send_button_click(self):
        for case in (
            self.module.case_upload_image,
            self.module.case_screenshot,
        ):
            with self.subTest(case=case.id):
                send = next(
                    item for item in self._steps(case)
                    if item.name.startswith("点击千问发送按钮")
                )
                self.assertEqual(send.kind, "ai")
                self.assertEqual(send.action_limits, {"click": 1})
                self.assertEqual(send.verify_mode, "change")
                self.assertFalse(send.retry_on_verify_fail)
                self.assertIn("绝对不要再次点击发送", send.payload)
                self.assertIn("输入框清空 + 新 AI 回复", send.payload)
                self.assertIn("新的 千问 AI 回复", send.verify)

    def test_one_shot_limits_cover_non_idempotent_attachment_actions(self):
        expected = {
            self.module.case_drag_document.id: {"click": 1, "drag": 1},
            self.module.case_upload_document.id: {"click": 2},
            self.module.case_upload_image.id: {"click": 2},
            self.module.case_copy_paste_document.id: {"hotkey": 1},
            self.module.case_screenshot.id: {"click": 3, "drag": 1},
        }
        prefixes = {
            self.module.case_drag_document.id: "拖拽本次唯一文档",
            self.module.case_upload_document.id: "打开千问附件菜单",
            self.module.case_upload_image.id: "打开千问附件菜单",
            self.module.case_copy_paste_document.id: "把唯一文档粘贴",
            self.module.case_screenshot.id: "使用千问“截屏提问”",
        }
        for case in self.cases:
            with self.subTest(case=case.id):
                stage = next(
                    item for item in self._steps(case)
                    if item.name.startswith(prefixes[case.id])
                )
                self.assertEqual(stage.action_limits, expected[case.id])
                self.assertIn("不要", stage.payload)

    def test_screenshot_notice_is_unique_without_sensitive_filename(self):
        ctx = SimpleNamespace(extras={})
        common._prepare_screenshot_notice(ctx)
        notice = ctx.extras[common._NOTICE_KEY]
        self.assertIn(common._TEST_NOTICE, notice)
        self.assertRegex(
            notice, r"测试标识：dlp_ai_screenshot_\d{6}_[0-9a-f]{3}$"
        )
        self.assertNotIn("sensitive_file", ctx.extras)

    def test_document_copy_is_unique_and_reported_as_sensitive_file(self):
        ctx = SimpleNamespace(extras={})
        with tempfile.TemporaryDirectory() as temp_dir:
            outbound_dir = Path(temp_dir) / "outbound"
            template = Path(temp_dir) / "template.txt"
            with (
                patch.object(common, "_SENSITIVE_DIR", str(outbound_dir)),
                patch.object(common, "_TEMPLATE_FILE", str(template)),
            ):
                common._make_document(ctx)

            files = list(outbound_dir.iterdir())
            self.assertEqual(len(files), 1)
            self.assertRegex(
                files[0].name,
                r"^dlp_ai_sample_\d{6}_[0-9a-f]{3}\.txt$",
            )
            self.assertEqual(ctx.extras["sensitive_file"], files[0].name)
            self.assertEqual(
                Path(ctx.extras[common._OUTBOUND_KEY]), files[0]
            )
            self.assertIn(
                "[dlp-ai-chat-marker]", files[0].read_text(encoding="utf-8")
            )

    def test_image_copy_uses_repository_template(self):
        ctx = SimpleNamespace(extras={})
        source = Path(self.module._APP.image_template)
        self.assertTrue(source.is_file())
        with tempfile.TemporaryDirectory() as temp_dir:
            outbound_dir = Path(temp_dir)
            with patch.object(common, "_SENSITIVE_DIR", str(outbound_dir)):
                common._make_image_fn(self.module._APP)(ctx)

            files = list(outbound_dir.iterdir())
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].suffix, source.suffix)
            self.assertEqual(files[0].read_bytes(), source.read_bytes())
            self.assertEqual(ctx.extras["sensitive_file"], files[0].name)


if __name__ == "__main__":
    unittest.main()
