"""Poe AI应用通道的纯逻辑回归测试（不启动 GUI）。

Poe 与千问/元宝/Kimi 共用 desktop_app.ai_chat 通道与 ai_chat_windows_common 脚手架，真机差异：
- 无「办公/日常模式」切换（required_mode 留空）；
- 主窗**标题恒为空**，只能靠进程名 poe.exe 强匹配——须登记进 apps._EMPTY_TITLE_APPS，
  _find_window 对其放行空标题窗口（这是千问/元宝/Kimi 都不需要、必须由测试固化的护栏）；
- 点“+”附件按钮**直接弹系统文件对话框**、没有二级菜单（attach_opens_dialog_directly=True），
  故上传步骤只点一次“+”、不点菜单项；
- 回车即发送（document_send_via_button=False），文档走「确定性回车发送 + presence 验收」，
  与千问/元宝一致；
- 比 Kimi 少一条截图 case，共 3 条（拖拽/上传/复制粘贴），且**不得**出现截图或单独图片 case。

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
        / "case_poe.py"
    )
    spec = importlib.util.spec_from_file_location(
        "test_case_poe_module", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 Poe case：{path}")
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


class PoeCaseFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load_case_module()
        cls.cases = (
            cls.module.case_drag_document,
            cls.module.case_upload_document,
            cls.module.case_copy_paste_document,
        )

    @staticmethod
    def _steps(case):
        return [item for item in case.define() if item is not None]

    def test_three_cases_use_dedicated_ai_chat_channel(self):
        """Poe 只有 3 条 case（比 Kimi 少截图），都走独立 ai_chat 通道。"""
        self.assertEqual(len(self.cases), 3)
        for case in self.cases:
            with self.subTest(case=case.id):
                self.assertEqual(case.channel, "desktop_app.ai_chat")
                self.assertTrue(case.id.startswith("desktop_app.ai_chat.poe."))
                self.assertEqual(case.app, "Poe")

    def test_no_screenshot_or_standalone_image_case(self):
        """比 Kimi 少一条截图 case；也不得有单独图片外发 case。"""
        ids = [case.id for case in self.cases]
        self.assertFalse(
            any("outbound_screenshot" in i for i in ids),
            f"Poe 不应有截图 case，实得：{ids}",
        )
        self.assertFalse(
            any("outbound_image" in i for i in ids),
            f"Poe 不应有单独图片 case，实得：{ids}",
        )

    def test_poe_app_registration_matches_localappdata_squirrel(self):
        self.assertEqual(windows_apps._title_hints("poe"), ["poe"])
        self.assertEqual(windows_apps._exe_names("poe"), ["poe.exe"])
        candidates = windows_apps._EXE_CANDIDATES["poe"]
        self.assertTrue(any(c.endswith("Poe.exe") for c in candidates))

    def test_poe_matches_empty_title_window_by_process_name(self):
        """Poe 主窗标题恒空：必须登记进 _EMPTY_TITLE_APPS 并放行空标题窗口。

        护栏：其它应用绝不能被放行空标题窗口（会误伤隐藏辅助窗），故 kimi/qianwen 必须 False。
        """
        self.assertIn("poe", windows_apps._EMPTY_TITLE_APPS)
        self.assertTrue(windows_apps._allow_empty_title("poe"))
        self.assertTrue(windows_apps._allow_empty_title("Poe"))  # 归一化大小写
        self.assertFalse(windows_apps._allow_empty_title("kimi"))
        self.assertFalse(windows_apps._allow_empty_title("qianwen"))

    def test_find_window_only_accepts_empty_title_with_opt_in_and_matching_exe(self):
        """空标题窗口必须同时满足显式放行和 exe 强匹配，缺一不可。"""
        import win32gui  # type: ignore

        hwnds = (101, 202)
        titles = {101: "", 202: ""}
        exes = {101: "poe.exe", 202: "helper.exe"}

        def enum_windows(callback, extra):
            for hwnd in hwnds:
                callback(hwnd, extra)

        with (
            patch.object(win32gui, "EnumWindows", side_effect=enum_windows),
            patch.object(win32gui, "IsWindowVisible", return_value=True),
            patch.object(
                win32gui, "GetWindowText",
                side_effect=lambda hwnd: titles[hwnd],
            ),
            patch.object(
                windows_apps, "_window_exe_basename",
                side_effect=lambda hwnd: exes[hwnd],
            ),
        ):
            self.assertIsNone(
                windows_apps._find_window(["poe"], ["poe.exe"])
            )
            self.assertEqual(
                windows_apps._find_window(
                    ["poe"], ["poe.exe"], allow_empty_title=True,
                ),
                101,
            )
            self.assertIsNone(
                windows_apps._find_window(
                    ["poe"], ["other.exe"], allow_empty_title=True,
                )
            )

    def test_empty_title_teardown_falls_back_to_quit_app(self):
        """按标题关不到 Poe 时，只对登记的空标题 app 用进程名解析主窗关闭。"""
        teardown = common.make_app_teardown(self.module._APP)
        with (
            patch.object(common.apps, "close_windows", return_value=0),
            patch.object(common.apps, "_allow_empty_title", return_value=True),
            patch.object(common.apps, "quit_app") as quit_app,
        ):
            teardown()
        quit_app.assert_called_once_with("poe")

    def test_poe_has_no_mode_switch_step(self):
        """Poe 无模式切换：required_mode 空，且三条 case 都没有模式确认 step。"""
        self.assertEqual(self.module._APP.required_mode, "")
        for case in self.cases:
            with self.subTest(case=case.id):
                names = [item.name for item in self._steps(case)]
                self.assertFalse(
                    any("处于" in n and "模式" in n for n in names),
                    f"Poe 不应有模式切换 step，实得：{names}",
                )

    def test_poe_relaunches_hidden_single_instance_window(self):
        """Poe 关窗后进程仍在、主窗销毁；重启只恢复原单实例主窗。"""
        self.assertTrue(self.module._APP.relaunch_if_hidden)
        ctx = SimpleNamespace(settings=None)
        with (
            patch.object(common.apps, "open_app") as open_app,
            patch.object(common.apps, "ensure_foreground"),
            patch.object(common.time, "sleep"),
        ):
            common._open_app_fn(self.module._APP)(ctx)
        open_app.assert_called_once_with(
            "poe",
            wait_sec=self.module._APP.open_wait_sec,
            relaunch_if_hidden=True,
        )

    def test_attach_opens_dialog_directly_no_menu_item(self):
        """Poe 点“+”直接弹文件对话框：上传步骤只点一次“+”、不点二级菜单项。"""
        app = self.module._APP
        self.assertTrue(app.attach_opens_dialog_directly)
        trigger = next(
            item for item in self._steps(self.module.case_upload_document)
            if item.name.startswith("点Poe“+”附件按钮直接唤起文件对话框")
        )
        # 明确“直接弹出、无二级菜单”，只点一次
        self.assertIn("直接弹出", trigger.payload)
        self.assertIn("没有二级菜单", trigger.payload)
        self.assertEqual(trigger.action_limits, {"click": 1})
        # 绝不能残留“在弹出的菜单中点击‘上传文档’”那套二级菜单提示
        self.assertNotIn("在弹出的菜单中点击", trigger.payload)

    def test_documents_send_via_enter_with_presence_verify(self):
        """Poe 回车即发送；验收还必须看到输入框清空和本次新 AI 回复。"""
        self.assertFalse(self.module._APP.document_send_via_button)
        for case in self.cases:
            with self.subTest(case=case.id):
                steps = self._steps(case)
                names = [item.name for item in steps]
                # 必须有一次“确定性回车发送”
                sends = [n for n in names if n.startswith("确定性回车发送")]
                self.assertEqual(len(sends), 1, f"实得：{names}")
                # 绝不能走“点发送按钮”路径（那是 Kimi 的回车不发送路径）
                self.assertFalse(
                    any(n.startswith("点击Poe发送按钮") for n in names),
                    f"Poe 文档应回车发送，实得：{names}",
                )
                send_index = next(
                    i for i, item in enumerate(steps)
                    if item.name.startswith("确定性回车发送")
                )
                observer = steps[send_index + 1]
                self.assertEqual(observer.verify_mode, "presence")
                self.assertIn("底部输入框已完全清空", observer.verify)
                self.assertIn("新的 Poe AI 回复", observer.verify)

    def test_app_name_never_falls_back_to_generic_ai_chat_key(self):
        """回归护栏：即便残留通用 ai_chat 键，Poe 也绝不能被解析成它。"""
        poe = self.module._APP
        settings = _FakeSettings({
            "platform": {"overrides": {"windows": {"app_names": {
                "ai_chat": "qianwen",  # 通用键残留，绝不能污染 Poe
            }}}}
        })
        ctx = SimpleNamespace(settings=settings)
        self.assertEqual(common._app_name(ctx, poe), "poe")

    def test_app_name_honors_app_key_specific_override(self):
        poe = self.module._APP
        settings = _FakeSettings({
            "platform": {"overrides": {"windows": {"app_names": {
                "ai_chat_poe": "custom_poe_key",
            }}}}
        })
        ctx = SimpleNamespace(settings=settings)
        self.assertEqual(common._app_name(ctx, poe), "custom_poe_key")

    def test_app_name_defaults_to_app_key_without_settings(self):
        poe = self.module._APP
        self.assertEqual(
            common._app_name(SimpleNamespace(settings=None), poe),
            "poe",
        )

    def test_composer_preflight_is_read_only_and_precedes_new_notice(self):
        for case in self.cases:
            with self.subTest(case=case.id):
                steps = self._steps(case)
                check_index = next(
                    i for i, item in enumerate(steps)
                    if item.name.startswith("确认 Poe 输入区为空")
                )
                notice_index = next(
                    i for i, item in enumerate(steps)
                    if item.name == "先在Poe输入区写入测试声明（暂不发送）"
                )
                check = steps[check_index]
                self.assertLess(check_index, notice_index)
                self.assertEqual(check.action_limits, {})

    def test_notice_precedes_attachment_and_each_flow_sends_once(self):
        attachment_prefixes = (
            "拖拽本次唯一文档",
            "点Poe“+”附件按钮直接唤起文件对话框",
            "把唯一文档粘贴进Poe输入区",
        )
        for case, prefix in zip(self.cases, attachment_prefixes):
            with self.subTest(case=case.id):
                steps = self._steps(case)
                notice_index = next(
                    i for i, item in enumerate(steps)
                    if item.name == "先在Poe输入区写入测试声明（暂不发送）"
                )
                attachment_index = next(
                    i for i, item in enumerate(steps)
                    if item.name.startswith(prefix)
                )
                sends = [
                    (i, item) for i, item in enumerate(steps)
                    if item.name.startswith("确定性回车发送")
                ]
                self.assertLess(notice_index, attachment_index)
                self.assertEqual(len(sends), 1)
                self.assertGreater(sends[0][0], attachment_index)


if __name__ == "__main__":
    unittest.main()
