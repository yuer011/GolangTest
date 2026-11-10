"""Windows app 级收尾策略回归测试（不操作真实进程）。"""
from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import yaml

from dlp_auto.actions._windows import apps as windows_apps
from dlp_auto.case import im_windows_common
from dlp_auto.case.runner import CaseRunner
from dlp_auto.config import Settings


_ROOT = Path(__file__).resolve().parents[1]


class AppTeardownConfigTests(unittest.TestCase):
    @staticmethod
    def _config() -> dict:
        with (_ROOT / "config" / "config.yaml").open(
            "r", encoding="utf-8",
        ) as fp:
            return yaml.safe_load(fp)

    def test_qianwen_closes_to_tray_and_welink_quits(self):
        config = self._config()

        self.assertTrue(config["teardown"]["enabled"])
        self.assertEqual(config["teardown"]["apps"]["千问"], "close")
        self.assertEqual(config["teardown"]["apps"]["WeLink"], "quit")

    def test_runner_reuses_qianwen_close_but_bypasses_welink_close_hook(self):
        runner = SimpleNamespace(settings=Settings(raw=self._config()))
        registered = Mock()
        with (
            patch(
                "dlp_auto.case.spec.get_app_teardown",
                return_value=registered,
            ),
            patch(
                "dlp_auto.actions.apps.app_teardown",
                return_value="[WeLink] done",
            ) as teardown,
        ):
            CaseRunner._run_app_teardown(runner, "千问")
            registered.assert_called_once_with()
            teardown.assert_not_called()

            registered.reset_mock()
            CaseRunner._run_app_teardown(runner, "WeLink")
            registered.assert_not_called()
            teardown.assert_called_once_with("WeLink", "quit")


class WindowsProcessTeardownTests(unittest.TestCase):
    def test_welink_quit_uses_verified_install_roots(self):
        expected_roots = [
            r"C:\Program Files (x86)\WeLink",
            r"C:\Program Files\WeLink",
        ]
        with (
            patch.object(windows_apps, "close_windows", return_value=1),
            patch.object(windows_apps.time, "sleep"),
            patch.object(
                windows_apps, "_kill_app_processes", side_effect=[2, 0],
            ) as kill,
        ):
            message = windows_apps.app_teardown("WeLink", "quit")

        self.assertEqual(
            kill.call_args_list,
            [
                call(["welink.exe"], roots=expected_roots),
                call(["welink.exe"], roots=expected_roots),
            ],
        )
        self.assertIn("结束 2 个残留进程", message)

    def test_quit_enumerates_windowless_processes_but_stays_in_safe_root(self):
        import win32api  # type: ignore
        import win32con  # type: ignore
        import win32process  # type: ignore

        paths = {
            101: r"C:\Program Files (x86)\WeLink\WeLink.exe",
            102: r"C:\Program Files (x86)\WeLink\daemonProcess.exe",
            103: r"C:\Other\WeLink.exe",
            104: None,
        }
        with (
            patch.object(
                win32process, "EnumProcesses", return_value=list(paths),
            ),
            patch.object(
                windows_apps,
                "_process_executable_path",
                side_effect=lambda pid: paths[pid],
            ),
            patch.object(
                win32api,
                "OpenProcess",
                side_effect=lambda _access, _inherit, pid: pid,
            ),
            patch.object(win32api, "TerminateProcess") as terminate,
            patch.object(win32api, "CloseHandle"),
        ):
            killed = windows_apps._kill_app_processes(
                ["welink.exe"],
                roots=[r"C:\Program Files (x86)\WeLink"],
            )

        self.assertEqual(killed, 2)
        terminate.assert_has_calls([call(101, 0), call(102, 0)], any_order=True)
        self.assertEqual(terminate.call_count, 2)
        self.assertEqual(win32con.PROCESS_TERMINATE, 1)


class WindowsAppLaunchTests(unittest.TestCase):
    def test_run_case_keeps_bom_and_parent_welink_cold_start(self):
        script_path = _ROOT / "scripts" / "run_case.ps1"
        raw = script_path.read_bytes()
        self.assertTrue(
            raw.startswith(b"\xef\xbb\xbf"),
            "含中文的 run_case.ps1 必须保留 UTF-8 BOM，供 Windows PowerShell 5 正确解析",
        )
        source = raw.decode("utf-8-sig")
        self.assertIn(
            "Start-Process -FilePath $WeLinkExe "
            "-WorkingDirectory $WeLinkDir -PassThru",
            source,
        )
        self.assertIn("Start-Sleep -Seconds 4", source)
        self.assertLess(
            source.index("Start-Process -FilePath $WeLinkExe"),
            source.index("Start-Process powershell -WorkingDirectory"),
        )

    def test_only_welink_starts_from_executable_directory(self):
        welink = r"C:\Program Files (x86)\WeLink\WeLink.exe"
        qianwen = r"C:\Users\test\AppData\Local\QianwenApp\qianwen.exe"
        with (
            patch.object(windows_apps.subprocess, "Popen") as popen,
        ):
            windows_apps._launch_exe("WeLink", welink)
            windows_apps._launch_exe("qianwen", qianwen)

        self.assertEqual(
            popen.call_args_list,
            [
                call(
                    [welink],
                    close_fds=True,
                    cwd=r"C:\Program Files (x86)\WeLink",
                ),
                call([qianwen], close_fds=True),
            ],
        )

    def test_im_open_requires_foreground_before_ai_steps(self):
        app = im_windows_common.ImApp(
            report_name="WeLink",
            app_key="welink",
            contacts_app="welink",
            target="测试联系人",
            target_kind="个人/会话",
            id_slug="welink",
            open_wait_sec=10.0,
        )
        ctx = SimpleNamespace(settings=None)
        with (
            patch.object(im_windows_common.apps, "open_app") as open_app,
            patch.object(
                im_windows_common.apps,
                "ensure_foreground",
                return_value=False,
            ),
            patch.object(im_windows_common.time, "sleep"),
        ):
            with self.assertRaisesRegex(RuntimeError, "避免模型误操作终端"):
                im_windows_common._make_open_app(app)(ctx)

        open_app.assert_called_once_with(
            "welink",
            wait_sec=10.0,
            wake_tray=None,
            tray_hints=None,
        )
        enter_step = im_windows_common._enter_conversation_steps(app)[1]
        self.assertIn("PowerShell/IDE", enter_step.payload)
        self.assertIn("绝对不要关闭", enter_step.payload)
