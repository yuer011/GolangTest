from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / ".trae"
    / "skills"
    / "sync-case-coverage"
    / "scripts"
    / "sync.py"
)
_SPEC = importlib.util.spec_from_file_location("sync_case_coverage", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
sync = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sync)


class LarkCliResolutionTests(unittest.TestCase):
    def test_windows_prefers_node_run_js_over_cmd_wrapper(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cmd = root / "lark-cli.cmd"
            run_js = (
                root
                / "node_modules"
                / "@larksuite"
                / "cli"
                / "scripts"
                / "run.js"
            )
            run_js.parent.mkdir(parents=True)
            run_js.touch()
            node = root / "node.exe"

            def which(name):
                return {
                    "lark-cli.cmd": str(cmd),
                    "node": str(node),
                }.get(name)

            with (
                patch.object(sync.sys, "platform", "win32"),
                patch.object(sync.shutil, "which", side_effect=which),
            ):
                resolved = sync._resolve_lark_cli()

        self.assertEqual(resolved, [str(node), str(run_js)])

    def test_windows_falls_back_to_cmd_when_run_js_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cmd = Path(temp_dir) / "lark-cli.cmd"
            with (
                patch.object(sync.sys, "platform", "win32"),
                patch.object(
                    sync.shutil,
                    "which",
                    side_effect=lambda name: (
                        str(cmd) if name == "lark-cli.cmd" else None
                    ),
                ),
            ):
                resolved = sync._resolve_lark_cli()

        self.assertEqual(resolved, [str(cmd)])


class CatalogReadTests(unittest.TestCase):
    def test_single_select_platform_is_normalized(self):
        with patch.object(
            sync,
            "_list_table_rows",
            return_value=[
                {
                    "record_id": "rec1",
                    "支持键": "qq@windows",
                    "飞连 App Key": "qq",
                    "支持端": ["Windows"],
                    "当前支持": True,
                }
            ],
        ):
            rows = sync._catalog_base_rows()
        self.assertEqual(rows[0]["支持端"], "Windows")

    def test_catalog_sync_maintains_drilldown_count_unit(self):
        source = {
            "key": "msedge@windows",
            "app_name": "Edge 浏览器",
            "app_key": "msedge",
            "channel_name": "浏览器",
            "channel_type": "browser",
            "platform": "Windows",
        }

        refreshed = sync._catalog_fields(
            source,
            {},
            version="1",
            commit="abc",
            now="2026-08-08 00:00:00",
        )
        daily = sync._coverage_fields(None)

        self.assertEqual(refreshed["统计单位"], 1)
        self.assertEqual(daily["统计单位"], 1)

    def test_catalog_sync_preserves_manual_adaptation_fields(self):
        source = {
            "key": "msedge@windows",
            "app_name": "Edge 浏览器",
            "app_key": "msedge",
            "channel_name": "浏览器",
            "channel_type": "browser",
            "platform": "Windows",
        }

        refreshed = sync._catalog_fields(
            source,
            {},
            version="1",
            commit="abc",
            now="2026-08-10 00:00:00",
        )
        daily = sync._coverage_fields(None)

        for fields in (refreshed, daily):
            self.assertNotIn("适配状态", fields)
            self.assertNotIn("适配说明", fields)


class CoverageMetricTests(unittest.TestCase):
    def test_priority_config_covers_current_channels(self):
        priority = sync._load_channel_priority()
        self.assertEqual(len(priority), 22)
        self.assertEqual(priority["im"], 1)
        self.assertEqual(priority["browser"], 2)
        self.assertEqual(priority["white"], 22)

    def test_unconfigured_channel_is_appended(self):
        priority, missing = sync._resolve_channel_priorities({"im", "new_channel"})
        self.assertEqual(missing, ["new_channel"])
        self.assertGreater(priority["new_channel"], priority["white"])

    def test_software_and_endpoint_denominators_are_separate(self):
        catalog = [
            {
                "支持键": "feishu@windows",
                "飞连 App Key": "feishu",
                "支持端": "Windows",
                "通道类型": "im",
                "通道名称": "即时通信",
                "当前支持": True,
                "源版本": "1",
            },
            {
                "支持键": "feishu@mac",
                "飞连 App Key": "feishu",
                "支持端": "Mac",
                "通道类型": "im",
                "通道名称": "即时通信",
                "当前支持": True,
                "源版本": "1",
            },
        ]
        metrics = {
            row["key"]: row
            for row in sync._metric_rows(
                catalog,
                {"feishu@windows": {"count": 1}},
            )
        }
        self.assertEqual(metrics["software@all"]["total"], 1)
        self.assertEqual(metrics["software@all"]["covered"], 1)
        self.assertEqual(metrics["endpoint@all"]["total"], 2)
        self.assertEqual(metrics["endpoint@all"]["covered"], 1)
        self.assertEqual(metrics["channel@im@windows"]["total"], 1)
        self.assertEqual(metrics["channel@im@windows"]["covered"], 1)
        self.assertEqual(metrics["channel@im@windows"]["platform"], "Windows")
        self.assertEqual(metrics["channel@im@mac"]["total"], 1)
        self.assertEqual(metrics["channel@im@mac"]["covered"], 0)
        self.assertEqual(metrics["channel@im@mac"]["platform"], "Mac")

    def test_channel_metrics_follow_configured_priority(self):
        catalog = [
            {
                "支持键": "mail@windows",
                "飞连 App Key": "mail",
                "支持端": "Windows",
                "通道类型": "email",
                "通道名称": "邮箱",
                "当前支持": True,
                "源版本": "1",
            },
            {
                "支持键": "feishu@windows",
                "飞连 App Key": "feishu",
                "支持端": "Windows",
                "通道类型": "im",
                "通道名称": "即时通信",
                "当前支持": True,
                "源版本": "1",
            },
        ]
        metrics = {
            row["key"]: row for row in sync._metric_rows(catalog, {})
        }
        self.assertLess(
            metrics["channel@im"]["order"],
            metrics["channel@email"]["order"],
        )
        self.assertLess(
            metrics["channel@im@windows"]["order"],
            metrics["channel@email@windows"]["order"],
        )
        self.assertEqual(
            metrics["channel@im"]["channel_sort_name"],
            "01 即时通信",
        )
        self.assertEqual(
            metrics["channel@email@windows"]["channel_sort_name"],
            "03 邮箱",
        )

    def test_explicit_wecom_alias_maps_to_feilian_wxwork(self):
        cases = [
            {
                "key": "desktop_app.im.wecom.outbound_file.drag_drop@windows",
                "app_slug": "wecom",
                "app": "企业微信",
                "scenario": "外发文件",
                "action": "拖拽",
                "platform": "Windows",
                "case_type": "正式",
                "metadata_status": "完整",
            }
        ]
        catalog = [
            {
                "支持键": "wxwork@windows",
                "飞连 App Key": "wxwork",
                "当前支持": True,
            }
        ]
        coverage, unmapped = sync._coverage_by_support_key(cases, catalog)
        self.assertEqual(unmapped, [])
        self.assertEqual(coverage["wxwork@windows"]["count"], 1)

    def test_explicit_aliww_alias_maps_to_feilian_aliwangwang(self):
        cases = [
            {
                "key": "desktop_app.im.aliww.outbound_image.upload@windows",
                "app_slug": "aliww",
                "app": "阿里旺旺",
                "scenario": "外发图片",
                "action": "对话框图片上传",
                "platform": "Windows",
                "case_type": "正式",
                "metadata_status": "完整",
            }
        ]
        catalog = [
            {
                "支持键": "aliwangwang@windows",
                "飞连 App Key": "aliwangwang",
                "当前支持": True,
            }
        ]
        coverage, unmapped = sync._coverage_by_support_key(cases, catalog)
        self.assertEqual(unmapped, [])
        self.assertEqual(coverage["aliwangwang@windows"]["count"], 1)

    def test_verified_browser_aliases_map_to_feilian_keys(self):
        aliases = {
            "360_safe": "360se",
            "360_speed": "360quick",
            "edge": "msedge",
            "qq_browser": "qqbrowser",
            "sogou": "sgbrowser",
        }
        cases = [
            {
                "key": f"web.other.{slug}.upload@windows",
                "app_slug": slug,
                "app": slug,
                "scenario": "HTTPS POST 文件上传",
                "action": "点击上传",
                "platform": "Windows",
                "case_type": "正式",
                "metadata_status": "完整",
            }
            for slug in aliases
        ]
        catalog = [
            {
                "支持键": f"{app_key}@windows",
                "飞连 App Key": app_key,
                "当前支持": True,
            }
            for app_key in aliases.values()
        ]

        coverage, unmapped = sync._coverage_by_support_key(cases, catalog)

        self.assertEqual(unmapped, [])
        self.assertEqual(
            set(coverage),
            {f"{app_key}@windows" for app_key in aliases.values()},
        )


if __name__ == "__main__":
    unittest.main()
