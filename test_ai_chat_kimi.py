"""Kimi AI应用通道的纯逻辑回归测试（不启动 GUI）。

Kimi 与千问/元宝共用 desktop_app.ai_chat 通道与 ai_chat_windows_common 脚手架，真机差异：
- 无「办公/日常模式」切换（required_mode 留空）；
- 文件与图片是**同一个上传入口**「添加文件和图片」，故只做一条上传 case（共 4 条，
  不含单独的上传图片）；
- 截图入口在「+」菜单里、文字含「截图」，且点该行后**自动完成截图**、无需框选/确认
  （screenshot_auto_capture=True）——这是千问（菜单里手动框选）和元宝（剪刀图标手动框选）
  都没有的行为，必须由测试固化。

本测试同样锁定 _app_name「绝不回退通用 ai_chat 键」的护栏，防止多 AI 应用互相错解析。
"""
from __future__ import annotations

import importlib.util
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
        / "case_kimi.py"
    )
    spec = importlib.util.spec_from_file_location(
        "test_case_kimi_module", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 Kimi case：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeSettings:
    """最小 Settings 桩：按 (*keys, default=) 读取嵌套字典。"""

    def __init__(self, data: dict):
        self._data = data

    def get(self, *keys, default=None):
        cur = self._data
        for key in keys:
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                return default
        return cur


class KimiCaseFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load_case_module()
        cls.cases = (
            cls.module.case_drag_document,
            cls.module.case_upload_document,
            cls.module.case_copy_paste_document,
            cls.module.case_screenshot,
        )

    @staticmethod
    def _steps(case):
        return [item for item in case.define() if item is not None]

    def test_four_cases_use_dedicated_ai_chat_channel(self):
        """Kimi 只有 4 条 case，且都走独立 ai_chat 通道（文件图片同入口，无单独上传图片）。"""
        self.assertEqual(len(self.cases), 4)
        for case in self.cases:
            with self.subTest(case=case.id):
                self.assertEqual(case.channel, "desktop_app.ai_chat")
                self.assertTrue(case.id.startswith("desktop_app.ai_chat.kimi."))
                self.assertEqual(case.app, "Kimi")

    def test_no_standalone_image_upload_case(self):
        """文件与图片共用一个入口，绝不能有 outbound_image 单独 case。"""
        ids = [case.id for case in self.cases]
        self.assertFalse(
            any("outbound_image" in i for i in ids),
            f"Kimi 不应有单独的图片外发 case，实得：{ids}",
        )

    def test_kimi_app_registration_matches_moonshot_kimi(self):
        self.assertEqual(windows_apps._title_hints("kimi"), ["kimi"])
        self.assertEqual(windows_apps._exe_names("kimi"), ["kimi.exe"])
        candidates = windows_apps._EXE_CANDIDATES["kimi"]
        self.assertTrue(any(c.endswith("Kimi.exe") for c in candidates))

    def test_kimi_has_no_mode_switch_step(self):
        """Kimi 无模式切换：required_mode 空，且四条 case 都没有模式确认 step。"""
        self.assertEqual(self.module._APP.required_mode, "")
        for case in self.cases:
            with self.subTest(case=case.id):
                names = [item.name for item in self._steps(case)]
                self.assertFalse(
                    any("处于" in n and "模式" in n for n in names),
                    f"Kimi 不应有模式切换 step，实得：{names}",
                )

    def test_upload_uses_single_file_and_image_entry(self):
        self.assertEqual(
            self.module._APP.upload_document_label, "添加文件和图片"
        )
        document_step = next(
            item for item in self._steps(self.module.case_upload_document)
            if item.name.startswith("打开Kimi附件菜单")
        )
        self.assertIn("添加文件和图片", document_step.payload)

    def test_screenshot_is_auto_capture_in_plus_menu(self):
        """Kimi 截图：在“+”菜单里，点含“截图”的行后自动截图、无需框选/对勾。"""
        app = self.module._APP
        self.assertTrue(app.screenshot_in_plus_menu)
        self.assertTrue(app.screenshot_auto_capture)
        stage = next(
            item for item in self._steps(self.module.case_screenshot)
            if item.name.startswith("使用Kimi")
        )
        # 走“+”菜单入口
        self.assertIn("点击输入框附近的“+”附件按钮", stage.payload)
        # 认准含“截图”字样的行（可能后跟软件名）
        self.assertIn("字样的那一行", stage.payload)
        # 自动截图：不需要框选、不需要点对勾
        self.assertIn("自动完成截图", stage.payload)
        self.assertIn("无需框选区域", stage.payload)
        # 绝不能残留“手动框选/点对勾”那套提示词
        self.assertNotIn("框选一个较大区域", stage.payload)
        self.assertNotIn("点击截图工具条的完成/对勾", stage.payload)
        # 自动截图只需点 2 次（+ 与截图行），不含 drag
        self.assertEqual(stage.action_limits, {"click": 2})

    def test_kimi_relaunches_hidden_single_instance_window(self):
        self.assertTrue(self.module._APP.relaunch_if_hidden)
        ctx = SimpleNamespace(settings=None)
        with (
            patch.object(common.apps, "open_app") as open_app,
            patch.object(common.apps, "ensure_foreground"),
            patch.object(common.time, "sleep"),
        ):
            common._open_app_fn(self.module._APP)(ctx)
        open_app.assert_called_once_with(
            "kimi",
            wait_sec=self.module._APP.open_wait_sec,
            relaunch_if_hidden=True,
        )

    def test_app_name_never_falls_back_to_generic_ai_chat_key(self):
        """回归护栏：即便残留通用 ai_chat 键，Kimi 也绝不能被解析成它。

        通用 ai_chat 键只能指向一款应用，多 AI 应用共用通道时回退它会互相错解析
        （曾把元宝错解析成千问、真机打开千问客户端，见 CHG-019 修复）。
        """
        kimi = self.module._APP
        settings = _FakeSettings({
            "platform": {"overrides": {"windows": {"app_names": {
                "ai_chat": "qianwen",  # 通用键残留，绝不能污染 Kimi
            }}}}
        })
        ctx = SimpleNamespace(settings=settings)
        self.assertEqual(common._app_name(ctx, kimi), "kimi")

    def test_app_name_honors_app_key_specific_override(self):
        kimi = self.module._APP
        settings = _FakeSettings({
            "platform": {"overrides": {"windows": {"app_names": {
                "ai_chat_kimi": "custom_kimi_key",
            }}}}
        })
        ctx = SimpleNamespace(settings=settings)
        self.assertEqual(
            common._app_name(ctx, kimi), "custom_kimi_key"
        )

    def test_app_name_defaults_to_app_key_without_settings(self):
        kimi = self.module._APP
        self.assertEqual(
            common._app_name(SimpleNamespace(settings=None), kimi),
            "kimi",
        )

    def test_composer_preflight_is_read_only_and_precedes_new_notice(self):
        for case in self.cases:
            with self.subTest(case=case.id):
                steps = self._steps(case)
                check_index = next(
                    i for i, item in enumerate(steps)
                    if item.name.startswith("确认 Kimi 输入区为空")
                )
                notice_index = next(
                    i for i, item in enumerate(steps)
                    if item.name == "先在Kimi输入区写入测试声明（暂不发送）"
                )
                check = steps[check_index]
                self.assertLess(check_index, notice_index)
                self.assertEqual(check.action_limits, {})

    def test_notice_precedes_attachment_and_each_flow_sends_once(self):
        attachment_prefixes = (
            "拖拽本次唯一文档",
            "打开Kimi附件菜单并选择“添加文件和图片”",
            "把唯一文档粘贴进Kimi输入区",
            "使用Kimi“截图”",
        )
        for case, prefix in zip(self.cases, attachment_prefixes):
            with self.subTest(case=case.id):
                steps = self._steps(case)
                notice_index = next(
                    i for i, item in enumerate(steps)
                    if item.name == "先在Kimi输入区写入测试声明（暂不发送）"
                )
                attachment_index = next(
                    i for i, item in enumerate(steps)
                    if item.name.startswith(prefix)
                )
                sends = [
                    (i, item) for i, item in enumerate(steps)
                    if (
                        item.name.startswith("确定性回车发送")
                        or item.name.startswith("点击Kimi发送按钮")
                    )
                ]
                self.assertLess(notice_index, attachment_index)
                self.assertEqual(len(sends), 1)
                self.assertGreater(sends[0][0], attachment_index)

    def test_documents_send_via_button_with_change_verify(self):
        """Kimi 回车不发送：三条文档 case 必须走「点发送按钮 + change 验收」，

        不能再用「确定性回车发送」（回车只换行、消息卡在输入框），验收要求聊天区新增
        我方消息、**输入框清空**且出现新的 AI 回复，避免 presence 误判同一对话里遗留的旧消息。
        """
        self.assertTrue(self.module._APP.document_send_via_button)
        document_cases = (
            self.module.case_drag_document,
            self.module.case_upload_document,
            self.module.case_copy_paste_document,
        )
        for case in document_cases:
            with self.subTest(case=case.id):
                steps = self._steps(case)
                names = [item.name for item in steps]
                # 绝不能残留「回车发送」路径
                self.assertFalse(
                    any(n.startswith("确定性回车发送") for n in names),
                    f"Kimi 文档不该用回车发送，实得：{names}",
                )
                send = next(
                    item for item in steps
                    if item.name.startswith("点击Kimi发送按钮发送测试声明和文档")
                )
                # change 验收（默认），不是 presence
                self.assertEqual(send.verify_mode, "change")
                self.assertEqual(send.action_limits, {"click": 1})
                # 验收硬性要求输入框清空
                self.assertIn("输入框此刻已完全清空", send.verify)
                # AI 聊天软件必须出现本次消息后的新回复，历史回复不能充数
                self.assertIn("新的 Kimi AI 回复", send.verify)
                # 明确禁止回车
                self.assertIn("不要按回车", send.payload)


if __name__ == "__main__":
    unittest.main()
