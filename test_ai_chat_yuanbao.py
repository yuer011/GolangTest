"""元宝 AI应用通道的纯逻辑回归测试（不启动 GUI）。

元宝与千问共用 desktop_app.ai_chat 通道与 ai_chat_windows_common 脚手架，但真机差异：
- 无「办公/日常模式」切换（required_mode 留空）；
- 附件菜单入口是「本地文件」「图片」（非千问的「上传文档」「上传图片」）；
- 截图入口是输入区工具栏的剪刀图标，不在「+」菜单里（screenshot_in_plus_menu=False）。

本测试尤其锁定 _app_name「绝不回退通用 ai_chat 键」的行为——该回退曾把元宝错解析成
千问、真机打开的是千问客户端（见 CHG-019 通道修复），必须由测试固化，防止再次回归。
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
        / "case_yuanbao.py"
    )
    spec = importlib.util.spec_from_file_location(
        "test_case_yuanbao_module", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载元宝 case：{path}")
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


class YuanbaoCaseFlowTests(unittest.TestCase):
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
                self.assertTrue(case.id.startswith("desktop_app.ai_chat.yuanbao."))
                self.assertEqual(case.app, "元宝")

    def test_yuanbao_app_registration_matches_tencent_yuanbao(self):
        self.assertEqual(windows_apps._title_hints("yuanbao"), ["元宝"])
        self.assertEqual(windows_apps._exe_names("yuanbao"), ["yuanbao.exe"])
        self.assertEqual(windows_apps._normalize_app_key("元宝"), "yuanbao")
        candidates = windows_apps._EXE_CANDIDATES["yuanbao"]
        self.assertTrue(any(c.endswith("yuanbao.exe") for c in candidates))

    def test_yuanbao_has_no_mode_switch_step(self):
        """元宝无模式切换：required_mode 空，且五条 case 都没有模式确认 step。"""
        self.assertEqual(self.module._APP.required_mode, "")
        for case in self.cases:
            with self.subTest(case=case.id):
                names = [item.name for item in self._steps(case)]
                self.assertFalse(
                    any("处于" in n and "模式" in n for n in names),
                    f"元宝不应有模式切换 step，实得：{names}",
                )

    def test_upload_menu_labels_are_local_file_and_image(self):
        self.assertEqual(self.module._APP.upload_document_label, "本地文件")
        self.assertEqual(self.module._APP.upload_image_label, "图片")
        document_step = next(
            item for item in self._steps(self.module.case_upload_document)
            if item.name.startswith("打开元宝附件菜单")
        )
        image_step = next(
            item for item in self._steps(self.module.case_upload_image)
            if item.name.startswith("打开元宝附件菜单")
        )
        self.assertIn("本地文件", document_step.payload)
        self.assertNotIn("图片", document_step.payload)
        self.assertIn("图片", image_step.payload)
        self.assertNotIn("本地文件", image_step.payload)

    def test_screenshot_entry_is_scissors_icon_not_in_plus_menu(self):
        self.assertFalse(self.module._APP.screenshot_in_plus_menu)
        stage = next(
            item for item in self._steps(self.module.case_screenshot)
            if item.name.startswith("使用元宝")
        )
        # 剪刀图标独立入口的提示词：明确不经过「+」附件菜单
        self.assertIn("不在“+”附件菜单里", stage.payload)
        self.assertNotIn("点击输入框附近的“+”附件按钮", stage.payload)
        self.assertEqual(stage.action_limits, {"click": 3, "drag": 1})

    def test_yuanbao_relaunches_hidden_single_instance_window(self):
        self.assertTrue(self.module._APP.relaunch_if_hidden)
        ctx = SimpleNamespace(settings=None)
        with (
            patch.object(common.apps, "open_app") as open_app,
            patch.object(common.apps, "ensure_foreground"),
            patch.object(common.time, "sleep"),
        ):
            common._open_app_fn(self.module._APP)(ctx)
        open_app.assert_called_once_with(
            "yuanbao",
            wait_sec=self.module._APP.open_wait_sec,
            relaunch_if_hidden=True,
        )

    def test_app_name_never_falls_back_to_generic_ai_chat_key(self):
        """回归护栏：即便残留通用 ai_chat 键，元宝也绝不能被解析成它。

        这是 CHG-019 通道修复的根因——旧 _app_name 在缺 ai_chat_<app_key> 时回退通用
        ai_chat 键（曾=qianwen），把元宝错解析成千问、真机打开千问客户端。
        """
        yuanbao = self.module._APP
        settings = _FakeSettings({
            "platform": {"overrides": {"windows": {"app_names": {
                "ai_chat": "qianwen",  # 通用键残留，绝不能污染元宝
            }}}}
        })
        ctx = SimpleNamespace(settings=settings)
        self.assertEqual(common._app_name(ctx, yuanbao), "yuanbao")

    def test_app_name_honors_app_key_specific_override(self):
        yuanbao = self.module._APP
        settings = _FakeSettings({
            "platform": {"overrides": {"windows": {"app_names": {
                "ai_chat_yuanbao": "custom_yuanbao_key",
            }}}}
        })
        ctx = SimpleNamespace(settings=settings)
        self.assertEqual(
            common._app_name(ctx, yuanbao), "custom_yuanbao_key"
        )

    def test_app_name_defaults_to_app_key_without_settings(self):
        yuanbao = self.module._APP
        self.assertEqual(
            common._app_name(SimpleNamespace(settings=None), yuanbao),
            "yuanbao",
        )

    def test_composer_preflight_is_read_only_and_precedes_new_notice(self):
        for case in self.cases:
            with self.subTest(case=case.id):
                steps = self._steps(case)
                check_index = next(
                    i for i, item in enumerate(steps)
                    if item.name.startswith("确认 元宝 输入区为空")
                )
                notice_index = next(
                    i for i, item in enumerate(steps)
                    if item.name == "先在元宝输入区写入测试声明（暂不发送）"
                )
                check = steps[check_index]
                self.assertLess(check_index, notice_index)
                self.assertEqual(check.action_limits, {})

    def test_notice_precedes_attachment_and_each_flow_sends_once(self):
        attachment_prefixes = (
            "拖拽本次唯一文档",
            "打开元宝附件菜单并选择“本地文件”",
            "打开元宝附件菜单并选择“图片”",
            "把唯一文档粘贴进元宝输入区",
            "使用元宝“截图”",
        )
        for case, prefix in zip(self.cases, attachment_prefixes):
            with self.subTest(case=case.id):
                steps = self._steps(case)
                notice_index = next(
                    i for i, item in enumerate(steps)
                    if item.name == "先在元宝输入区写入测试声明（暂不发送）"
                )
                attachment_index = next(
                    i for i, item in enumerate(steps)
                    if item.name.startswith(prefix)
                )
                sends = [
                    (i, item) for i, item in enumerate(steps)
                    if (
                        item.name.startswith("确定性回车发送")
                        or item.name.startswith("点击元宝发送按钮")
                    )
                ]
                self.assertLess(notice_index, attachment_index)
                self.assertEqual(len(sends), 1)
                self.assertGreater(sends[0][0], attachment_index)


if __name__ == "__main__":
    unittest.main()
