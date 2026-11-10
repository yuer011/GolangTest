"""macOS Web 浏览器通道的纯逻辑回归测试（不启动 GUI）。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from dlp_auto.case import web_mac_common as common
from dlp_auto.case.web_dlptest_mac import (
    _site_url,
    click_upload_steps,
    drag_drop_steps,
)
from dlp_auto.case.web_mac_common import BrowserApp
from dlp_auto.config import Settings

_APP = BrowserApp(
    report_name="测试浏览器",
    app_key="test_browser",
)


def _ctx(raw: dict) -> SimpleNamespace:
    return SimpleNamespace(settings=Settings(raw=raw), extras={})


class MacBrowserConfigTests(unittest.TestCase):
    def test_requires_explicit_browser_config(self):
        with self.assertRaisesRegex(TypeError, "web.browsers.mac.test_browser"):
            common._browser_config(_ctx({}), _APP)

    def test_requires_bundle_id_and_verified_protocol(self):
        with tempfile.TemporaryDirectory() as d:
            exe = Path(d) / "browser"
            exe.touch()
            raw = {
                "web": {
                    "browsers": {
                        "mac": {
                            "test_browser": {
                                "executable": str(exe),
                                "launch_protocol": "chromium_isolated",
                            },
                        },
                    },
                },
            }
            with self.assertRaisesRegex(ValueError, "bundle_id"):
                common._browser_config(_ctx(raw), _APP)

            raw["web"]["browsers"]["mac"]["test_browser"]["bundle_id"] = (
                "com.example.browser"
            )
            raw["web"]["browsers"]["mac"]["test_browser"][
                "launch_protocol"
            ] = "guessed_protocol"
            with self.assertRaisesRegex(ValueError, "尚未实现"):
                common._browser_config(_ctx(raw), _APP)

    def test_launch_args_are_protocol_specific(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            exe = root / "browser"
            profile = root / "profile"
            chromium = common._BrowserConfig(
                executable=exe,
                bundle_id="com.example.chromium",
                launch_protocol="chromium_isolated",
                window_wait_sec=15,
            )
            firefox = common._BrowserConfig(
                executable=exe,
                bundle_id="org.example.firefox",
                launch_protocol="firefox_isolated",
                window_wait_sec=15,
            )

            chromium_args = common._launch_args(
                chromium, profile, "https://example.test/"
            )
            firefox_args = common._launch_args(
                firefox, profile, "https://example.test/"
            )

        self.assertIn(f"--user-data-dir={profile}", chromium_args)
        self.assertIn("--new-window", chromium_args)
        self.assertIn("-no-remote", firefox_args)
        self.assertEqual(
            firefox_args[firefox_args.index("-profile") + 1],
            str(profile),
        )

    def test_site_url_must_come_from_config_and_use_https(self):
        with self.assertRaisesRegex(ValueError, "https_post_url"):
            _site_url(_ctx({}))
        with self.assertRaisesRegex(ValueError, "https://"):
            _site_url(_ctx({
                "web": {
                    "sites": {
                        "dlptest": {"https_post_url": "http://example.test/"},
                    },
                },
            }))
        url = _site_url(_ctx({
            "web": {
                "sites": {
                    "dlptest": {
                        "https_post_url": "https://example.test/https-post/",
                    },
                },
            },
        }))
        self.assertEqual(url, "https://example.test/https-post/")


class _FakeSession:
    def __init__(self):
        self.navigate_calls: list[str] = []
        self.close_calls = 0

    def is_window_alive(self):
        return True

    def navigate(self, url):
        self.navigate_calls.append(url)

    def close(self):
        self.close_calls += 1


class MacBrowserSessionRegistryTests(unittest.TestCase):
    def setUp(self):
        common._SESSIONS.clear()
        common._CONFIG_CACHE.clear()

    def tearDown(self):
        common._SESSIONS.clear()
        common._CONFIG_CACHE.clear()

    def test_each_case_closes_previous_session_and_launches_new_window(self):
        first = _FakeSession()
        second = _FakeSession()
        ctx = _ctx({})
        with patch.object(
            common,
            "_launch_session",
            side_effect=[first, second],
        ) as launch:
            common.open_or_reset_browser(ctx, _APP, "https://example.test/one")
            common.open_or_reset_browser(ctx, _APP, "https://example.test/two")

        self.assertEqual(launch.call_count, 2)
        launch.assert_any_call(ctx, _APP, "https://example.test/one")
        launch.assert_any_call(ctx, _APP, "https://example.test/two")
        self.assertEqual(first.close_calls, 1)
        self.assertIs(common._SESSIONS[_APP.app_key], second)
        self.assertEqual(first.navigate_calls, [])
        self.assertEqual(second.navigate_calls, [])

    def test_teardown_closes_only_registered_session_and_is_idempotent(self):
        fake = _FakeSession()
        common._SESSIONS[_APP.app_key] = fake
        teardown = common.make_browser_teardown(_APP)

        teardown()
        teardown()

        self.assertEqual(fake.close_calls, 1)
        self.assertNotIn(_APP.app_key, common._SESSIONS)

    def test_navigation_pastes_complete_url_instead_of_typing(self):
        url = "https://example.test/https-post/?case=mac-browser"
        fake = SimpleNamespace(
            app=_APP,
            activate_and_maximize=lambda: None,
        )
        with (
            patch.object(common.keyboard, "hotkey") as hotkey,
            patch.object(common.keyboard, "type_text") as type_text,
            patch.object(common.clipboard, "set_text") as set_text,
            patch.object(common.clipboard, "get_text", return_value=url),
            patch.object(common, "_post_native_command_key") as command_key,
            patch.object(common, "_post_native_return") as submit,
            patch.object(common.time, "sleep"),
        ):
            common._BrowserSession.navigate(fake, url)

        hotkey.assert_called_once_with("command", "l")
        type_text.assert_not_called()
        set_text.assert_called_once_with(url)
        self.assertEqual(
            [call.args[0] for call in command_key.call_args_list],
            [0, 9],
        )
        submit.assert_called_once_with()

    def test_startup_prompt_is_optional_ai_step_before_centering(self):
        default_names = [
            item.name for item in click_upload_steps(_APP)
            if item is not None
        ]
        self.assertNotIn("关闭 测试浏览器 首次启动弹窗", default_names)

        prompted = BrowserApp(
            report_name="测试浏览器",
            app_key="test_browser",
            startup_prompt_instruction="关闭所有首次启动弹窗",
        )
        steps = click_upload_steps(prompted)
        names = [item.name for item in steps if item is not None]

        self.assertEqual(names[1], "关闭 测试浏览器 首次启动弹窗")
        self.assertEqual(names[2], "上传前将 File upload 卡片居中")
        self.assertEqual(steps[1].verify_mode, "presence")

    def test_submit_allows_one_correction_and_browser_is_reactivated(self):
        for steps in (drag_drop_steps(_APP), click_upload_steps(_APP)):
            submit_index = next(
                index for index, item in enumerate(steps)
                if (
                    item is not None
                    and item.name.startswith("点击 File upload 的 Submit")
                )
            )
            submit = steps[submit_index]
            activate = steps[submit_index - 1]
            self.assertEqual(submit.action_limits, {"click": 2, "scroll": 1})
            self.assertEqual(
                activate.name,
                "提交前重新激活 测试浏览器 受管窗口",
            )
            self.assertEqual(activate.kind, "hard")
            self.assertEqual(
                steps[-1].name,
                "<cleanup>",
            )


class MacUploadFileTests(unittest.TestCase):
    def test_case_owns_unique_dir_and_reports_sensitive_filename(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            first_ctx = _ctx({})
            second_ctx = _ctx({})
            with (
                patch.object(common, "_TMP_ROOT", root),
                patch.object(
                    common,
                    "_TEMPLATE_FILE",
                    root / "dlp_web_sample_template.txt",
                ),
                patch.object(common, "_UPLOAD_ROOT", root / "web_upload"),
            ):
                common.make_unique_upload_file(first_ctx, _APP)
                common.make_unique_upload_file(second_ctx, _APP)
                first = common.outbound_file(first_ctx)
                second = common.outbound_file(second_ctx)

                self.assertNotEqual(first, second)
                self.assertNotEqual(first.parent, second.parent)
                for ctx, path in (
                    (first_ctx, first),
                    (second_ctx, second),
                ):
                    self.assertTrue(path.is_file())
                    self.assertGreater(path.stat().st_size, 0)
                    self.assertEqual(list(path.parent.iterdir()), [path])
                    self.assertEqual(
                        ctx.extras["sensitive_file"], path.name
                    )
                    common.cleanup_upload_file(ctx)
                    self.assertFalse(path.parent.exists())


if __name__ == "__main__":
    unittest.main()
