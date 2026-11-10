"""Windows Web 浏览器通道的纯逻辑回归测试（不启动 GUI）。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from dlp_auto.case import web_windows_common as common
from dlp_auto.case.web_dlptest_windows import (
    _site_url,
    click_upload_steps,
    drag_drop_steps,
)
from dlp_auto.case.web_windows_common import BrowserApp
from dlp_auto.config import Settings


_APP = BrowserApp(
    report_name="测试浏览器",
    app_key="test_browser",
)


def _ctx(raw: dict) -> SimpleNamespace:
    return SimpleNamespace(settings=Settings(raw=raw), extras={})


class BrowserConfigTests(unittest.TestCase):
    def test_requires_explicit_browser_config(self):
        with self.assertRaisesRegex(ValueError, "web.browsers.windows.test_browser"):
            common._browser_config(_ctx({}), _APP)

    def test_rejects_unverified_launch_protocol(self):
        with tempfile.TemporaryDirectory() as d:
            exe = Path(d) / "browser.exe"
            exe.touch()
            ctx = _ctx({
                "web": {
                    "browsers": {
                        "windows": {
                            "test_browser": {
                                "executable": str(exe),
                                "launch_protocol": "guessed_protocol",
                            },
                        },
                    },
                },
            })
            with self.assertRaisesRegex(ValueError, "尚未实现"):
                common._browser_config(ctx, _APP)

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
                        "https_post_url": "https://dlptest.example/https-post/",
                    },
                },
            },
        }))
        self.assertEqual(url, "https://dlptest.example/https-post/")

    def test_full_process_cleanup_requires_verified_root_containing_exe(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            exe = root / "app" / "browser.exe"
            exe.parent.mkdir()
            exe.touch()
            base = {
                "executable": str(exe),
                "launch_protocol": "chromium_isolated",
                "process_cleanup": {"mode": "all_under_roots"},
            }
            ctx = _ctx({
                "web": {
                    "browsers": {
                        "windows": {"test_browser": base},
                    },
                },
            })
            with self.assertRaisesRegex(ValueError, "必须配置 roots"):
                common._browser_config(ctx, _APP)

            outside = root / "outside"
            outside.mkdir()
            base["process_cleanup"]["roots"] = [str(outside)]
            with self.assertRaisesRegex(ValueError, "不在任何进程清理根目录"):
                common._browser_config(ctx, _APP)

            base["process_cleanup"]["roots"] = [str(exe.parent)]
            config = common._browser_config(ctx, _APP)
            self.assertEqual(config.cleanup_mode, "all_under_roots")
            self.assertEqual(config.cleanup_roots, (exe.parent,))

    def test_launch_args_are_protocol_specific(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            exe = root / "browser.exe"
            profile = root / "profile"
            config = common._BrowserConfig(
                executable=exe,
                launch_protocol="firefox_isolated",
                window_wait_sec=15,
                cleanup_mode="all_under_roots",
                cleanup_roots=(root,),
            )
            args = common._launch_args(
                config, profile, "https://example.test/"
            )

        self.assertEqual(args[0], str(exe))
        self.assertIn("-no-remote", args)
        self.assertEqual(args[args.index("-profile") + 1], str(profile))
        self.assertNotIn("--user-data-dir", " ".join(args))


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


class BrowserSessionRegistryTests(unittest.TestCase):
    def setUp(self):
        common._SESSIONS.clear()
        common._CONFIG_CACHE.clear()

    def tearDown(self):
        common._SESSIONS.clear()
        common._CONFIG_CACHE.clear()

    def test_first_case_launches_and_second_case_reuses_same_window(self):
        fake = _FakeSession()
        ctx = _ctx({})
        with patch.object(common, "_launch_session", return_value=fake) as launch:
            common.open_or_reset_browser(ctx, _APP, "https://example.test/one")
            common.open_or_reset_browser(ctx, _APP, "https://example.test/two")

        launch.assert_called_once_with(ctx, _APP, "https://example.test/one")
        self.assertIs(common._SESSIONS[_APP.app_key], fake)
        self.assertEqual(
            fake.navigate_calls, ["https://example.test/two"]
        )

    def test_teardown_closes_only_registered_session_and_is_idempotent(self):
        fake = _FakeSession()
        common._SESSIONS[_APP.app_key] = fake
        teardown = common.make_browser_teardown(_APP)

        teardown()
        teardown()

        self.assertEqual(fake.close_calls, 1)
        self.assertNotIn(_APP.app_key, common._SESSIONS)

    def test_teardown_without_session_still_clears_configured_processes(self):
        config = common._BrowserConfig(
            executable=Path("C:/Browser/browser.exe"),
            launch_protocol="chromium_isolated",
            window_wait_sec=15,
            cleanup_mode="all_under_roots",
            cleanup_roots=(Path("C:/Browser"),),
        )
        common._CONFIG_CACHE[_APP.app_key] = config
        teardown = common.make_browser_teardown(_APP)

        with patch.object(common, "_kill_processes_under_roots") as kill:
            teardown()

        kill.assert_called_once_with(
            _APP,
            config.cleanup_roots,
            phase="case 组结束",
        )
        self.assertNotIn(_APP.app_key, common._CONFIG_CACHE)

    def test_startup_prompt_is_optional_ai_step_before_centering(self):
        default_names = [
            item.name for item in click_upload_steps(_APP)
            if item is not None
        ]
        self.assertNotIn("关闭 测试浏览器 首次启动弹窗", default_names)

        prompted_app = BrowserApp(
            report_name="测试浏览器",
            app_key="test_browser",
            startup_prompt_instruction="关闭所有首次启动弹窗",
        )
        steps = click_upload_steps(prompted_app)
        names = [item.name for item in steps]

        self.assertEqual(names[1], "关闭 测试浏览器 首次启动弹窗")
        self.assertEqual(names[2], "上传前将 File upload 卡片居中")
        self.assertEqual(steps[1].kind, "ai")
        self.assertEqual(steps[1].verify_mode, "presence")

    def test_submit_allows_only_one_scroll_when_button_is_not_visible(self):
        submit = next(
            item for item in click_upload_steps(_APP)
            if (
                item is not None
                and item.name.startswith("点击 File upload 的 Submit")
            )
        )
        self.assertIn("向下滚动**一次**", submit.payload)
        self.assertIn("滚动一次后绝对不能再滚动", submit.payload)
        self.assertEqual(submit.action_limits, {"click": 1, "scroll": 1})

    def test_browser_is_reactivated_immediately_before_submit(self):
        for steps in (drag_drop_steps(_APP), click_upload_steps(_APP)):
            submit_index = next(
                index for index, item in enumerate(steps)
                if (
                    item is not None
                    and item.name.startswith("点击 File upload 的 Submit")
                )
            )
            activate = steps[submit_index - 1]
            self.assertEqual(
                activate.name,
                "提交前重新激活 测试浏览器 受管窗口",
            )
            self.assertEqual(activate.kind, "hard")


class BrowserProcessCleanupTests(unittest.TestCase):
    def test_kill_retries_until_no_configured_process_remains(self):
        roots = (Path("C:/Browser"),)
        running = {
            101: Path("C:/Browser/browser.exe"),
            102: Path("C:/Browser/helper.exe"),
        }
        with (
            patch.object(
                common,
                "_processes_under_roots",
                side_effect=[running, {}, {}],
            ),
            patch.object(common.subprocess, "run") as run,
            patch.object(common.time, "sleep"),
        ):
            killed = common._kill_processes_under_roots(
                _APP, roots, phase="测试"
            )

        self.assertEqual(killed, 2)
        self.assertEqual(run.call_count, 2)


class UploadFileTests(unittest.TestCase):
    def test_case_owns_unique_dir_and_reports_sensitive_filename(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            ctx = _ctx({})
            with (
                patch.object(common, "_TMP_ROOT", root),
                patch.object(
                    common, "_TEMPLATE_FILE", root / "dlp_web_sample_template.txt"
                ),
                patch.object(common, "_UPLOAD_ROOT", root / "web_upload"),
            ):
                common.make_unique_upload_file(ctx, _APP)
                path = common.outbound_file(ctx)
                self.assertTrue(path.is_file())
                self.assertEqual(list(path.parent.iterdir()), [path])
                self.assertEqual(ctx.extras["sensitive_file"], path.name)

                common.cleanup_upload_file(ctx)
                self.assertFalse(path.parent.exists())


if __name__ == "__main__":
    unittest.main()
