"""独立回归执行层与 R40/R41 水印 case 的纯逻辑测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from dlp_auto.case.loader import PythonModuleLoader
from dlp_auto.config import Settings
from dlp_auto.core.judge import Verdict
from dlp_auto.core.platform import CURRENT
from dlp_auto.core.run_context import RunContext
from dlp_auto.regression.admin_web_mac import (
    admin_login_steps,
    admin_page_url,
    open_admin_page,
)
from dlp_auto.regression.loader import RegressionLoader
from dlp_auto.regression.report import RegressionReportWriter
from dlp_auto.regression.resources import RegressionRunResources
from dlp_auto.regression.runner import RegressionRunner
from dlp_auto.regression.spec import (
    AssertionSpec,
    RegressionCaseSpec,
    RegressionStepContext,
    SourceCheck,
    ai_step,
    hard_step,
    resolve_text,
)


class _Screen:
    def __init__(self):
        self.out_dir = None
        self.calls = 0

    def capture(self, *, persist=False, name=None):
        self.calls += 1
        path = None
        if persist:
            path = Path(self.out_dir) / f"{name}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"png")
        return SimpleNamespace(b64=f"shot-{self.calls}", path=path)


class _Agent:
    def __init__(self):
        self.screen = _Screen()
        self.instructions: list[str] = []
        self.kwargs: list[dict] = []

    def do(self, instruction, *_args, **_kwargs):
        self.instructions.append(instruction)
        self.kwargs.append(_kwargs)
        return SimpleNamespace(
            ok=True,
            reason="finished",
            steps=1,
            trajectory=[],
        )


class _Judge:
    def __init__(self, verdicts):
        self.verdicts = list(verdicts)
        self.assertions: list[str] = []

    def verify_presence(self, assertion, _after):
        self.assertions.append(assertion)
        return self.verdicts.pop(0)


def _context(root: Path) -> RunContext:
    return RunContext(
        run_id=RunContext.new_run_id(),
        platform=CURRENT,
        settings=Settings(),
        report_dir=root,
        log_dir=root,
        screenshot_root=root,
    )


class RegressionIsolationTests(unittest.TestCase):
    def test_main_loader_excludes_regression_tree(self):
        repository = Path(__file__).resolve().parents[1]
        cases = PythonModuleLoader().load(repository / "cases")

        self.assertFalse(any(case.id.startswith("regression.") for case in cases))

    def test_main_loader_rejects_explicit_regression_path(self):
        repository = Path(__file__).resolve().parents[1]
        with self.assertRaisesRegex(ValueError, "regression"):
            PythonModuleLoader().load(repository / "cases" / "regression")

    def test_regression_loader_finds_watermark_case_only(self):
        repository = Path(__file__).resolve().parents[1]
        cases = RegressionLoader().load(repository / "cases" / "regression")

        self.assertEqual(
            [case.id for case in cases],
            ["regression.screen_watermark.create_preview_save"],
        )
        step_names = [step.name for step in cases[0].steps]
        self.assertLess(
            step_names.index("R40 点击预览并保留预览状态"),
            step_names.index("R41 单次确认添加并验证策略保存"),
        )
        consent = next(step for step in cases[0].steps if step.name == "按用户授权确认登录协议")
        self.assertEqual(consent.action_limits, {"click": 1})
        password_prompt = next(
            step for step in cases[0].steps if step.name == "关闭浏览器保存密码提示"
        )
        self.assertEqual(password_prompt.action_limits, {"click": 1})
        self.assertTrue(cases[0].reflect)
        preview = next(step for step in cases[0].steps if step.name == "R40 点击预览并保留预览状态")
        self.assertEqual(preview.action_limits, {"click": 1})
        save = next(
            step for step in cases[0].steps if step.name == "R41 单次确认添加并验证策略保存"
        )
        self.assertEqual(save.action_limits, {"click": 1})
        self.assertEqual(save.evidence_ref, "r41_policy_saved")
        self.assertEqual(
            [(item.source_ref, item.required_assertions) for item in cases[0].source_checks],
            [
                ("R40", ("preview_visible",)),
                ("R41", ("policy_saved",)),
            ],
        )


class RegressionRunnerTests(unittest.TestCase):
    def test_run_finalizes_shared_resources(self):
        resources = SimpleNamespace(finalize=Mock())

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = _context(root)
            RegressionRunner(
                context=context,
                agent=_Agent(),
                judge=_Judge([]),
                writer=RegressionReportWriter(root / context.run_id),
                resources=resources,
            ).run([])

        resources.finalize.assert_called_once_with()

    def test_step_condition_skips_ai_and_hard_actions(self):
        called: list[str] = []
        case = RegressionCaseSpec(
            id="regression.conditional",
            name="conditional",
            platforms=(CURRENT,),
            steps=(
                hard_step(
                    "skip hard",
                    lambda _ctx: called.append("hard"),
                    when=lambda _ctx: False,
                ),
                ai_step(
                    "skip ai",
                    "must not run",
                    when=lambda _ctx: False,
                ),
                hard_step(
                    "run hard",
                    lambda _ctx: called.append("run"),
                    when=lambda _ctx: True,
                ),
            ),
            assertions=(),
            source_checks=(),
        )
        agent = _Agent()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = _context(root)
            RegressionRunner(
                context=context,
                agent=agent,
                judge=_Judge([]),
                writer=RegressionReportWriter(root / context.run_id),
            ).run([case])

        self.assertEqual(called, ["run"])
        self.assertEqual(agent.instructions, [])

    def test_reflect_persists_only_under_regression_hint_tree(self):
        case = RegressionCaseSpec(
            id="regression.screen_watermark.reflect_demo",
            name="reflect",
            platforms=(CURRENT,),
            steps=(ai_step("configure", "configure once"),),
            assertions=(),
            source_checks=(),
            reflect=True,
        )
        agent = _Agent()
        reflection_llm = SimpleNamespace(
            chat=Mock(
                return_value=(
                    '{"hints":["use the regression-only path"],'
                    '"optimized_instruction":"","rationale":"stable"}'
                )
            )
        )
        registry = SimpleNamespace(default=reflection_llm)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hints_root = root / "cases" / ".hints"
            context = _context(root)
            with (
                patch(
                    "dlp_auto.core.reflect._HINTS_ROOT",
                    hints_root,
                ),
                patch(
                    "dlp_auto.core.reflect._REPORT",
                    root / ".tmp" / "reflect_report.md",
                ),
            ):
                RegressionRunner(
                    context=context,
                    agent=agent,
                    judge=_Judge([]),
                    writer=RegressionReportWriter(root / context.run_id),
                    llm_registry=registry,
                ).run([case])

            expected = (
                hints_root / "regression" / "screen_watermark" / CURRENT.value / "reflect_demo.yaml"
            )
            self.assertTrue(expected.is_file())
            self.assertEqual(
                [path.relative_to(hints_root) for path in hints_root.rglob("*") if path.is_file()],
                [expected.relative_to(hints_root)],
            )

    def test_reflect_uses_regression_only_hint_namespace(self):
        case = RegressionCaseSpec(
            id="regression.screen_watermark.reflect_demo",
            name="reflect",
            platforms=(CURRENT,),
            steps=(ai_step("configure", "configure once"),),
            assertions=(),
            source_checks=(),
            reflect=True,
        )
        agent = _Agent()
        reflector = SimpleNamespace(reflect=Mock())
        registry = SimpleNamespace(default=object())

        with (
            tempfile.TemporaryDirectory() as directory,
            patch(
                "dlp_auto.regression.runner.load_hints",
                return_value=["known path"],
            ) as load_hints,
            patch(
                "dlp_auto.regression.runner.Reflector",
                return_value=reflector,
            ),
        ):
            root = Path(directory)
            context = _context(root)
            RegressionRunner(
                context=context,
                agent=agent,
                judge=_Judge([]),
                writer=RegressionReportWriter(root / context.run_id),
                llm_registry=registry,
            ).run([case])

        self.assertEqual(agent.kwargs[0]["hints"], ["known path"])
        load_hints.assert_called_once_with(
            case.id,
            "configure",
            channel="regression.screen_watermark",
            platform=CURRENT.value,
        )
        reflector.reflect.assert_called_once()
        call = reflector.reflect.call_args.kwargs
        self.assertEqual(call["channel"], "regression.screen_watermark")
        self.assertEqual(call["platform"], CURRENT.value)

    def test_one_case_maps_sequential_evidence_to_r40_and_r41(self):
        case = RegressionCaseSpec(
            id="regression.demo",
            name="demo",
            platforms=(CURRENT,),
            steps=(
                ai_step("preview", "preview", evidence_ref="preview"),
                ai_step("save", "save", evidence_ref="saved"),
            ),
            assertions=(
                AssertionSpec(
                    name="preview_visible",
                    checker="ui_state",
                    assertion_set="preview visible",
                    evidence_ref="preview",
                ),
                AssertionSpec(
                    name="policy_saved",
                    checker="ui_state",
                    assertion_set="policy saved",
                    evidence_ref="saved",
                ),
            ),
            source_checks=(
                SourceCheck("R40", ("preview_visible",)),
                SourceCheck("R41", ("policy_saved",)),
            ),
        )
        agent = _Agent()
        judge = _Judge(
            [
                Verdict("passed", "preview ok"),
                Verdict("failed", "save missing"),
            ]
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = _context(root)
            writer = RegressionReportWriter(root / context.run_id)
            report = RegressionRunner(
                context=context,
                agent=agent,
                judge=judge,
                writer=writer,
            ).run([case])

            result = report.cases[0]
            self.assertEqual(
                [(item.source_ref, item.status) for item in result.source_checks],
                [("R40", "passed"), ("R41", "failed")],
            )
            self.assertEqual(result.status, "failed")
            self.assertEqual(agent.instructions, ["preview", "save"])
            self.assertTrue(writer.results_path.is_file())
            self.assertTrue(writer.summary_path.is_file())
            self.assertTrue(writer.html_path.is_file())

    def test_assertion_failure_does_not_repeat_gui_action(self):
        case = RegressionCaseSpec(
            id="regression.no-retry",
            name="no retry",
            platforms=(CURRENT,),
            steps=(ai_step("save", "save once", evidence_ref="saved"),),
            assertions=(
                AssertionSpec(
                    name="saved",
                    checker="ui_state",
                    assertion_set="saved",
                    evidence_ref="saved",
                ),
            ),
            source_checks=(SourceCheck("R41", ("saved",)),),
        )
        agent = _Agent()
        judge = _Judge([Verdict("inconclusive", "judge error")])

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = _context(root)
            RegressionRunner(
                context=context,
                agent=agent,
                judge=judge,
                writer=RegressionReportWriter(root / context.run_id),
            ).run([case])

        self.assertEqual(agent.instructions, ["save once"])

    def test_failed_preview_stops_dependent_save_but_keeps_r40_result(self):
        case = RegressionCaseSpec(
            id="regression.dependent",
            name="dependent",
            platforms=(CURRENT,),
            steps=(
                ai_step("preview", "preview", evidence_ref="preview"),
                ai_step("save", "save", evidence_ref="saved"),
            ),
            assertions=(
                AssertionSpec(
                    name="preview_visible",
                    checker="ui_state",
                    assertion_set="preview visible",
                    evidence_ref="preview",
                ),
                AssertionSpec(
                    name="policy_saved",
                    checker="ui_state",
                    assertion_set="policy saved",
                    evidence_ref="saved",
                ),
            ),
            source_checks=(
                SourceCheck("R40", ("preview_visible",)),
                SourceCheck("R41", ("policy_saved",)),
            ),
            reflect=True,
        )
        agent = _Agent()
        judge = _Judge([Verdict("failed", "preview missing")])
        registry = SimpleNamespace(default=object())

        with (
            tempfile.TemporaryDirectory() as directory,
            patch("dlp_auto.regression.runner.Reflector") as reflector,
        ):
            root = Path(directory)
            context = _context(root)
            result = (
                RegressionRunner(
                    context=context,
                    agent=agent,
                    judge=judge,
                    writer=RegressionReportWriter(root / context.run_id),
                    llm_registry=registry,
                )
                .run([case])
                .cases[0]
            )

        self.assertEqual(agent.instructions, ["preview"])
        reflector.assert_not_called()
        self.assertEqual(
            [(item.source_ref, item.status) for item in result.source_checks],
            [("R40", "failed"), ("R41", "inconclusive")],
        )


class WatermarkCaseSafetyTests(unittest.TestCase):
    @staticmethod
    def _admin_settings() -> Settings:
        return Settings(
            raw={
                "regression": {
                    "admin": {
                        "base_url": "https://example.test",
                        "admin_user": "admin-user",
                        "admin_pwd": "admin-password",
                    },
                    "screen_watermark": {
                        "admin_path": "/admin/watermark?mode=create",
                    },
                },
            }
        )

    def test_admin_url_combines_shared_environment_and_case_path(self):
        repository = Path(__file__).resolve().parents[1]
        case = RegressionLoader().load(repository / "cases" / "regression")[0]
        ctx = RegressionStepContext(
            case=case,
            settings=self._admin_settings(),
            run_id="run-id",
        )

        self.assertEqual(
            admin_page_url(
                ctx,
                "regression",
                "screen_watermark",
                "admin_path",
            ),
            "https://example.test/admin/watermark?mode=create",
        )

    def test_admin_url_rejects_external_case_url(self):
        repository = Path(__file__).resolve().parents[1]
        case = RegressionLoader().load(repository / "cases" / "regression")[0]
        settings = self._admin_settings()
        settings.raw["regression"]["screen_watermark"]["admin_path"] = (
            "https://unexpected.test/admin"
        )
        ctx = RegressionStepContext(
            case=case,
            settings=settings,
            run_id="run-id",
        )

        with self.assertRaisesRegex(ValueError, "站内路径"):
            admin_page_url(
                ctx,
                "regression",
                "screen_watermark",
                "admin_path",
            )

    def test_reused_admin_session_skips_all_login_steps(self):
        repository = Path(__file__).resolve().parents[1]
        case = RegressionLoader().load(repository / "cases" / "regression")[0]
        resources = SimpleNamespace(
            open_or_reuse_admin_browser=Mock(return_value=False),
        )
        ctx = RegressionStepContext(
            case=case,
            settings=self._admin_settings(),
            run_id="run-id",
            resources=resources,
        )

        with patch("dlp_auto.regression.admin_web_mac.time.sleep"):
            open_admin_page(
                ctx,
                "https://example.test/admin/watermark?mode=create",
            )

        login_steps = admin_login_steps()
        self.assertTrue(login_steps)
        self.assertTrue(all(step.when is not None for step in login_steps))
        self.assertTrue(all(not step.when(ctx) for step in login_steps))

    def test_secrets_are_not_interpolated_into_ai_instructions(self):
        repository = Path(__file__).resolve().parents[1]
        case = RegressionLoader().load(repository / "cases" / "regression")[0]
        secret_phone = "19999999999"
        secret_password = "do-not-leak"
        ctx = RegressionStepContext(
            case=case,
            settings=Settings(
                raw={
                    "regression": {
                        "admin": {
                            "base_url": "https://example.test",
                            "admin_user": "admin",
                            "admin_pwd": secret_password,
                        },
                        "screen_watermark": {
                            "admin_path": "/admin",
                            "policy_name_prefix": "watermark",
                            "custom_text": "custom",
                            "opacity_percent": 15,
                            "employee_phone": secret_phone,
                        },
                    },
                }
            ),
            run_id="run-id",
        )
        case.steps[0].payload(ctx)
        instructions = [resolve_text(step.payload, ctx) for step in case.steps if step.kind == "ai"]

        self.assertTrue(instructions)
        self.assertNotIn(secret_phone, "\n".join(instructions))
        self.assertNotIn(secret_password, "\n".join(instructions))

    def test_credentials_are_injected_only_by_hard_step(self):
        repository = Path(__file__).resolve().parents[1]
        case = RegressionLoader().load(repository / "cases" / "regression")[0]
        inject_user = next(step for step in case.steps if step.name == "注入管理员账号")
        inject_password = next(step for step in case.steps if step.name == "注入管理员密码并登录")
        ctx = RegressionStepContext(
            case=case,
            settings=Settings(
                raw={
                    "regression": {
                        "admin": {
                            "base_url": "https://example.test",
                            "admin_user": "admin-user",
                            "admin_pwd": "admin-password",
                        },
                        "screen_watermark": {
                            "admin_path": "/admin",
                        },
                    },
                }
            ),
            run_id="run-id",
        )
        with (
            patch("dlp_auto.actions._mac.keyboard.type_text") as type_text,
            patch("dlp_auto.actions._mac.keyboard.hotkey") as hotkey,
            patch("dlp_auto.actions._mac.keyboard.paste") as paste,
            patch("dlp_auto.actions._mac.keyboard.press_enter") as enter,
            patch("dlp_auto.actions._mac.clipboard.set_text") as set_text,
            patch("time.sleep"),
        ):
            inject_user.payload(ctx)
            inject_password.payload(ctx)

        type_text.assert_called_once_with("admin-user")
        self.assertEqual(
            [call.args for call in hotkey.call_args_list],
            [("command", "a"), ("command", "a")],
        )
        paste.assert_called_once_with()
        enter.assert_called_once_with()
        self.assertEqual(
            [call.args[0] for call in set_text.call_args_list],
            ["admin-password", ""],
        )


class RegressionRunResourcesTests(unittest.TestCase):
    def test_reuses_admin_browser_within_one_run(self):
        resources = RegressionRunResources()
        app = SimpleNamespace(app_key="chrome", report_name="Chrome")
        ctx = SimpleNamespace()

        with (
            patch("dlp_auto.case.web_mac_common.open_or_reset_browser") as open_browser,
            patch(
                "dlp_auto.case.web_mac_common.browser_session_alive",
                return_value=True,
            ),
            patch("dlp_auto.case.web_mac_common.navigate_browser") as navigate_browser,
            patch("dlp_auto.case.web_mac_common.close_browser_session") as close_browser,
        ):
            self.assertTrue(
                resources.open_or_reuse_admin_browser(
                    ctx,
                    app,
                    "https://example.test/first",
                )
            )
            self.assertFalse(
                resources.open_or_reuse_admin_browser(
                    ctx,
                    app,
                    "https://example.test/second",
                )
            )
            resources.finalize()

        open_browser.assert_called_once_with(
            ctx,
            app,
            "https://example.test/first",
        )
        navigate_browser.assert_called_once_with(
            app,
            "https://example.test/second",
        )
        close_browser.assert_called_once_with(app)

    def test_keep_browser_open_skips_run_finalizer_close(self):
        resources = RegressionRunResources(keep_browser_open=True)
        app = SimpleNamespace(app_key="chrome", report_name="Chrome")

        with (
            patch("dlp_auto.case.web_mac_common.open_or_reset_browser"),
            patch("dlp_auto.case.web_mac_common.close_browser_session") as close_browser,
        ):
            resources.open_or_reuse_admin_browser(
                SimpleNamespace(),
                app,
                "https://example.test",
            )
            resources.finalize()

        close_browser.assert_not_called()


if __name__ == "__main__":
    unittest.main()
