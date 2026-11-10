"""阿里旺旺专属图片外发流程的纯逻辑回归测试（不启动 GUI）。"""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from dlp_auto.case import im_windows_common as common


def _load_case_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "cases"
        / "desktop_app"
        / "im"
        / "windows"
        / "case_aliww.py"
    )
    spec = importlib.util.spec_from_file_location("test_case_aliww_module", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载阿里旺旺 case：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AliwwCaseFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load_case_module()
        cls.cases = (
            cls.module.case_drag_drop,
            cls.module.case_upload,
            cls.module.case_copy_paste,
            cls.module.case_screenshot,
        )

    @staticmethod
    def _steps(case):
        return [item for item in case.define() if item is not None]

    def test_all_four_flows_paste_caption_before_staging_image(self):
        stage_names = (
            "拖拽本次唯一图片",
            "点开阿里旺旺图片上传入口",
            "把本次图片粘贴进输入框",
            "用阿里旺旺自带截图功能",
        )
        for case, stage_prefix in zip(self.cases, stage_names):
            with self.subTest(case=case.id):
                steps = self._steps(case)
                caption_index = next(
                    i for i, item in enumerate(steps)
                    if item.name == "先把本次图片文件名粘贴到阿里旺旺输入框"
                )
                stage_index = next(
                    i for i, item in enumerate(steps)
                    if item.name.startswith(stage_prefix)
                )
                self.assertLess(caption_index, stage_index)

    def test_each_flow_has_exactly_one_hard_enter(self):
        for case in self.cases:
            with self.subTest(case=case.id):
                steps = self._steps(case)
                sends = [
                    (i, item) for i, item in enumerate(steps)
                    if item.name.startswith("确定性回车发送")
                ]
                self.assertEqual(len(sends), 1)
                _, send = sends[0]
                self.assertEqual(send.kind, "hard")

    def test_manual_flows_send_after_staging_then_use_read_only_observer(self):
        for case in self.cases:
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
                self.assertIn("绝对不要点击", observer.payload)
                self.assertIn("没有任何补发权限", observer.payload)
                self.assertIn("文字和图片二者缺一不可", observer.verify)

    def test_drag_restores_window_and_confirms_preview_before_hard_send(self):
        steps = self._steps(self.module.case_drag_drop)
        send_index = next(
            i for i, item in enumerate(steps)
            if item.name.startswith("确定性回车发送")
        )
        drag_index = next(
            i for i, item in enumerate(steps)
            if item.name.startswith("拖拽本次唯一图片")
        )
        drag = steps[drag_index]
        close_index = next(
            i for i, item in enumerate(steps)
            if item.name == "拖拽后关闭 dlp_test 资源管理器"
        )
        restore_index = next(
            i for i, item in enumerate(steps)
            if item.name == "恢复阿里旺旺分屏前窗口尺寸并置前"
        )
        confirm_index = next(
            i for i, item in enumerate(steps)
            if item.name.startswith("恢复窗口后确认文件名和图片预览")
        )

        self.assertLess(drag_index, close_index)
        self.assertLess(close_index, restore_index)
        self.assertLess(restore_index, confirm_index)
        self.assertLess(confirm_index, send_index)
        self.assertEqual(drag.kind, "ai")
        self.assertEqual(drag.verify_mode, "change")
        self.assertFalse(drag.retry_on_verify_fail)
        self.assertIn("图片预览可能被遮住", drag.payload)
        self.assertIn("不要再次拖拽", drag.payload)
        self.assertIsNone(drag.verify)
        self.assertEqual(steps[close_index].kind, "hard")
        self.assertEqual(steps[restore_index].kind, "hard")
        self.assertEqual(steps[confirm_index].kind, "ai")
        self.assertIn("直接 call_user", steps[confirm_index].payload)

    def test_one_shot_action_limits_block_duplicate_image_staging(self):
        expected_limits = {
            self.module.case_drag_drop.id: {"click": 1, "drag": 1},
            self.module.case_upload.id: {"click": 2},
            self.module.case_copy_paste.id: {"hotkey": 1},
            self.module.case_screenshot.id: {"click": 2, "drag": 1},
        }
        stage_markers = {
            self.module.case_drag_drop.id: "拖拽本次唯一图片",
            self.module.case_upload.id: "点开阿里旺旺图片上传入口",
            self.module.case_copy_paste.id: "把本次图片粘贴进输入框",
            self.module.case_screenshot.id: "用阿里旺旺自带截图功能",
        }
        for case in self.cases:
            with self.subTest(case=case.id):
                stage = next(
                    item for item in self._steps(case)
                    if item.name.startswith(stage_markers[case.id])
                )
                self.assertEqual(stage.action_limits, expected_limits[case.id])
                self.assertIn("不要", stage.payload)

    def test_screenshot_caption_does_not_turn_case_into_filename_matching(self):
        ctx = SimpleNamespace(extras={})
        with patch.object(self.module.clipboard, "set_text") as set_text:
            self.module._prepare_screenshot_caption(ctx)

        caption = ctx.extras[self.module._CAPTION_KEY]
        self.assertRegex(caption, r"^dlp_screenshot_\d{6}_[0-9a-f]{3}\.png$")
        self.assertNotIn("sensitive_file", ctx.extras)
        set_text.assert_called_once_with(caption)

    def test_drag_restore_uses_the_recorded_pre_split_rectangle(self):
        ctx = SimpleNamespace(
            settings=None,
            extras={self.module._DRAG_WINDOW_RECT_KEY: (100, 120, 900, 720)},
        )
        with (
            patch.object(
                self.module.apps, "move_resize", return_value=True
            ) as move_resize,
            patch.object(self.module.time, "sleep"),
        ):
            self.module._restore_after_drag(ctx)

        move_resize.assert_called_once_with(
            "aliww", 100, 120, 800, 600, front=True
        )

    def test_image_copy_uses_repo_asset_and_leaves_one_unique_png(self):
        ctx = SimpleNamespace(extras={})
        source = Path(self.module._SAMPLE_POOL[0])
        self.assertTrue(source.is_file())

        with tempfile.TemporaryDirectory() as temp_dir:
            outbound_dir = Path(temp_dir)
            (outbound_dir / "dlp_sample_old.txt").write_text(
                "old", encoding="utf-8"
            )
            with (
                patch.object(common, "_SENSITIVE_DIR", str(outbound_dir)),
                patch.object(common.random, "choice", return_value=str(source)),
            ):
                common._copy_step(self.module._APP).payload(ctx)

            files = list(outbound_dir.iterdir())
            self.assertEqual(len(files), 1)
            self.assertRegex(
                files[0].name, r"^dlp_sample_\d{6}_[0-9a-f]{3}\.png$"
            )
            self.assertEqual(files[0].read_bytes(), source.read_bytes())
            self.assertEqual(ctx.extras["sensitive_file"], files[0].name)
            self.assertEqual(
                Path(ctx.extras[common._OUTBOUND_KEY]), files[0]
            )


if __name__ == "__main__":
    unittest.main()
