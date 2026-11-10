"""独立回归 runner：顺序执行动作，并对冻结截图做只读断言。"""

from __future__ import annotations

import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dlp_auto.core.reflect import Reflector, load_hints
from dlp_auto.core.run_context import RunContext

from .assertions import evaluate_ui_state
from .report import (
    AssertionResult,
    RegressionCaseResult,
    RegressionReportWriter,
    RegressionRunResult,
    SourceResult,
)
from .resources import RegressionRunResources
from .spec import (
    AssertionSpec,
    RegressionCaseSpec,
    RegressionStep,
    RegressionStepContext,
    resolve_text,
)


class RegressionRunner:
    def __init__(
        self,
        *,
        context: RunContext,
        agent: Any,
        judge: Any,
        writer: RegressionReportWriter,
        llm_registry: Any = None,
        reflect: bool | None = None,
        resources: RegressionRunResources | None = None,
    ):
        self.context = context
        self.agent = agent
        self.judge = judge
        self.writer = writer
        self.llm = llm_registry
        self.reflect = reflect
        self.resources = resources or RegressionRunResources()
        self._reflector = None
        self._last_ai_result = None
        self._last_ai_instruction = ""

    def run(self, cases: list[RegressionCaseSpec]) -> RegressionRunResult:
        started = datetime.now(timezone.utc)
        report = RegressionRunResult(
            run_id=self.context.run_id,
            platform=self.context.platform.value,
            started_at=started.isoformat(timespec="seconds"),
        )
        self.writer.open()
        try:
            for case in cases:
                result = self.run_one(case)
                report.cases.append(result)
                self.writer.append_case(result)
        finally:
            try:
                self.writer.close()
            finally:
                self.resources.finalize()
        report.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.writer.write_final(report)
        return report

    def run_one(self, case: RegressionCaseSpec) -> RegressionCaseResult:
        print(f"\n========== REGRESSION {case.id} ==========")
        print(f"  {case.name}")
        started = datetime.now(timezone.utc)
        t0 = time.perf_counter()
        result = RegressionCaseResult(
            id=case.id,
            name=case.name,
            platform=self.context.platform.value,
            started_at=started.isoformat(timespec="seconds"),
        )
        if self.context.platform not in case.platforms:
            result.execution_status = "skipped"
            result.status = "skipped"
            result.issue = (
                f"当前平台 {self.context.platform.value} 不在 "
                f"{[item.value for item in case.platforms]}"
            )
            return self._finish(result, t0)

        ctx = RegressionStepContext(
            case=case,
            settings=self.context.settings,
            run_id=self.context.run_id,
            resources=self.resources,
        )
        assertions_by_evidence = self._assertions_by_evidence(case)
        evaluated: set[str] = set()
        cleanups = [step for step in case.steps if step.kind == "cleanup"]
        old_out_dir = getattr(self.agent.screen, "out_dir", None)
        self.agent.screen.out_dir = self._case_screenshot_dir(case.id)

        try:
            for step in case.steps:
                if step.kind == "cleanup":
                    continue
                if step.when is not None and not step.when(ctx):
                    print(f"\n  -- [skip] {step.name}")
                    continue
                self._last_ai_result = None
                self._last_ai_instruction = ""
                if not self._run_step(step, ctx):
                    result.execution_status = "failed"
                    result.issue = f"步骤「{step.name}」未完成"
                    break
                assertion_ok = True
                if step.evidence_ref:
                    assertion_ok = self._evaluate_evidence(
                        step.evidence_ref,
                        assertions_by_evidence.get(step.evidence_ref, []),
                        ctx,
                        result,
                        evaluated,
                    )
                    if not assertion_ok and not step.continue_on_assertion_failure:
                        result.issue = f"断言「{step.evidence_ref}」未通过，未执行后续依赖步骤"
                        break
                if step.kind == "ai" and assertion_ok:
                    self._reflect_success(case, step)
        except Exception:  # noqa: BLE001
            result.execution_status = "error"
            result.error = traceback.format_exc()
            result.issue = "回归 case 执行异常（详见 error）"
            print(f"  💥 回归 case 异常：\n{result.error}")
        finally:
            for step in cleanups:
                try:
                    if step.when is not None and not step.when(ctx):
                        continue
                    step.payload(ctx)
                except Exception:  # noqa: BLE001
                    detail = traceback.format_exc()
                    print(f"  ⚠️ cleanup 异常：\n{detail}")
                    if result.execution_status == "passed":
                        result.execution_status = "error"
                        result.issue = "cleanup 异常"
                        result.error = detail
            self.agent.screen.out_dir = old_out_dir

        for assertion in case.assertions:
            if assertion.name in evaluated:
                continue
            result.assertions.append(
                AssertionResult(
                    name=assertion.name,
                    checker=assertion.checker,
                    status="inconclusive",
                    detail="关联步骤未完成，未取得冻结截图证据",
                    evidence_ref=assertion.evidence_ref,
                )
            )

        result.policy_name = str(ctx.extras.get("policy_name") or "")
        result.source_checks = self._source_results(case, result.assertions)
        result.status = self._case_status(result)
        return self._finish(result, t0)

    def _run_step(
        self,
        step: RegressionStep,
        ctx: RegressionStepContext,
    ) -> bool:
        print(f"\n  -- [{step.kind}] {step.name}")
        if step.kind == "hard":
            step.payload(ctx)
            return True
        if step.kind == "ai":
            before_ai_step = ctx.extras.get("before_ai_step")
            before_step = (lambda: before_ai_step(ctx)) if callable(before_ai_step) else None
            instruction = resolve_text(step.payload, ctx)
            hints = self._load_hints(ctx.case.id, step.name)
            if hints:
                print(f"     🧠 注入 {len(hints)} 条回归历史经验")
            result = self.agent.do(
                instruction,
                ctx,
                hints=hints,
                action_limits=step.action_limits,
                before_step=before_step,
                policy="none",
            )
            if not result.ok:
                print(f"     ai 未成功：reason={result.reason} steps={result.steps}")
            self._last_ai_result = result
            self._last_ai_instruction = instruction
            return bool(result.ok)
        raise ValueError(f"不支持的回归 step kind：{step.kind}")

    def _reflect_enabled(self, case: RegressionCaseSpec) -> bool:
        if self.reflect is None:
            return bool(case.reflect)
        return self.reflect

    @staticmethod
    def _hint_namespace(case_id: str) -> str:
        parts = case_id.split(".")
        return ".".join(parts[:-1]) if len(parts) > 1 else "regression"

    def _load_hints(self, case_id: str, step_name: str) -> list[str]:
        try:
            return load_hints(
                case_id,
                step_name,
                channel=self._hint_namespace(case_id),
                platform=self.context.platform.value,
            )
        except Exception:  # noqa: BLE001
            return []

    def _reflect_success(
        self,
        case: RegressionCaseSpec,
        step: RegressionStep,
    ) -> None:
        result = self._last_ai_result
        if not self._reflect_enabled(case) or self.llm is None or result is None:
            return
        if self._reflector is None:
            self._reflector = Reflector(self.llm.default)
        try:
            self._reflector.reflect(
                case_id=case.id,
                step_name=step.name,
                instruction=self._last_ai_instruction,
                trajectory=result.trajectory,
                steps=result.steps,
                channel=self._hint_namespace(case.id),
                platform=self.context.platform.value,
            )
        except Exception:  # noqa: BLE001
            print(f"     ⚠️ 回归反思失败（忽略）：\n{traceback.format_exc()}")

    def _evaluate_evidence(
        self,
        evidence_ref: str,
        assertions: list[AssertionSpec],
        ctx: RegressionStepContext,
        result: RegressionCaseResult,
        evaluated: set[str],
    ) -> bool:
        if not assertions:
            return True
        settle = max(item.settle_timeout_sec for item in assertions)
        if settle > 0:
            time.sleep(settle)
        before_ai_step = ctx.extras.get("before_ai_step")
        if callable(before_ai_step):
            before_ai_step(ctx)
        shot = self.agent.screen.capture(
            persist=True,
            name=evidence_ref,
        )
        screenshot = self._relative_screenshot(shot.path)
        for assertion in assertions:
            try:
                if assertion.checker != "ui_state":
                    raise ValueError(f"尚未实现 checker={assertion.checker!r}")
                verdict = evaluate_ui_state(
                    assertion,
                    ctx,
                    image_b64=shot.b64,
                    judge=self.judge,
                )
                status = verdict.status
                detail = verdict.reason
            except Exception as exc:  # noqa: BLE001
                status = "inconclusive"
                detail = f"断言执行异常：{type(exc).__name__}: {exc}"
            result.assertions.append(
                AssertionResult(
                    name=assertion.name,
                    checker=assertion.checker,
                    status=status,
                    detail=detail,
                    evidence_ref=evidence_ref,
                    screenshot=screenshot,
                )
            )
            evaluated.add(assertion.name)
            print(f"  🔎 [{assertion.name}] {status}: {detail}")
        return all(
            item.status == "passed"
            for item in result.assertions
            if item.evidence_ref == evidence_ref
        )

    @staticmethod
    def _assertions_by_evidence(
        case: RegressionCaseSpec,
    ) -> dict[str, list[AssertionSpec]]:
        result: dict[str, list[AssertionSpec]] = {}
        for assertion in case.assertions:
            if not assertion.evidence_ref:
                raise ValueError(f"断言 {assertion.name!r} 缺少 evidence_ref")
            result.setdefault(assertion.evidence_ref, []).append(assertion)
        return result

    @staticmethod
    def _source_results(
        case: RegressionCaseSpec,
        assertions: list[AssertionResult],
    ) -> list[SourceResult]:
        by_name = {item.name: item.status for item in assertions}
        results: list[SourceResult] = []
        for source in case.source_checks:
            statuses = [by_name.get(name, "inconclusive") for name in source.required_assertions]
            if statuses and all(status == "passed" for status in statuses):
                status = "passed"
            elif any(status == "failed" for status in statuses):
                status = "failed"
            else:
                status = "inconclusive"
            results.append(
                SourceResult(
                    source_ref=source.source_ref,
                    status=status,
                    required_assertions=list(source.required_assertions),
                )
            )
        return results

    @staticmethod
    def _case_status(result: RegressionCaseResult) -> str:
        if result.execution_status in {"error", "skipped", "failed"}:
            return result.execution_status
        statuses = [item.status for item in result.source_checks]
        if statuses and all(status == "passed" for status in statuses):
            return "passed"
        if any(status == "failed" for status in statuses):
            return "failed"
        return "inconclusive"

    def _case_screenshot_dir(self, case_id: str) -> Path:
        safe = case_id.replace("/", "_").replace(" ", "_")
        path = self.writer.screenshot_dir / safe
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _relative_screenshot(self, path: Path | None) -> str:
        if path is None:
            return ""
        try:
            return str(path.relative_to(self.writer.run_dir))
        except ValueError:
            return str(path)

    @staticmethod
    def _finish(
        result: RegressionCaseResult,
        started_perf: float,
    ) -> RegressionCaseResult:
        result.duration_ms = int((time.perf_counter() - started_perf) * 1000)
        result.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        print(
            f"  => 回归 case 结果：{result.status}"
            f"（执行={result.execution_status}，耗时={result.duration_ms}ms）"
        )
        return result
