"""VerificationManager：编排三路验收并聚合到 case 结论。

三路结论各占一列写入 CaseReport.extras["checks"]（dict: name -> CheckOutcome as dict）。
聚合语义（唯一）：
    - execution_status 单独记录动作执行结果，不与 DLP 控制结论混淆。
    - DLP 日志/服务端 checker 是控制面验收；视觉只记录执行证据，不计入控制结论。
    - 所有已启用控制面 checker 都 passed 才能得到最终 passed；
      任一 failed → failed；缺失/inconclusive/skipped → inconclusive。
    - 「可有可无 / 未实装」的验收路以「不启用（不进 expected_names）」表达，
      而不是返回假 pass——未启用任何控制面 checker 时最终为 inconclusive，
      禁止仅凭动作执行成功输出「没有发现问题」。
"""
from __future__ import annotations

from dataclasses import asdict

from .aggregator import OutcomeAggregator
from .outcome import CheckContext, CheckOutcome


class VerificationManager:
    def __init__(self, *, case_checkers=None, app_checkers=None,
                 run_checkers=None, policy: str = "none"):
        self.case_checkers = list(case_checkers or [])   # scope="case"
        self.app_checkers = list(app_checkers or [])     # scope="app"
        self.run_checkers = list(run_checkers or [])     # scope="run"
        # 本次运行声明的预期策略（none/audit/block）。none=不启用策略感知，
        # 聚合逐字节回退现状；见 docs/dlp_policy_assertion_design.md §3/§6。
        self.policy = policy or "none"

    @property
    def enabled(self) -> bool:
        return bool(self.case_checkers or self.app_checkers or self.run_checkers)

    def on_case_start(self, ctx: CheckContext) -> None:
        # 把本次运行策略注入上下文，供 case 级 checker 选用对应类型特征。
        # 由 manager 注入（而非 runner），使 runner 不感知策略断言。
        ctx.policy = self.policy
        for c in self.case_checkers:
            if hasattr(c, "on_case_start"):
                try:
                    c.on_case_start(ctx)
                except Exception as e:  # noqa: BLE001
                    print(f"  ⚠️ checker {c.name}.on_case_start 异常（忽略）：{e}")

    # ── 每个 case 跑完：跑 case 级 checker，聚合 ───────────────────────
    def on_case_finished(self, ctx: CheckContext) -> None:
        rep = ctx.rep
        for c in self.case_checkers:
            outcome = self._safe_check(c, ctx)
            self._record(rep, outcome)
            print(f"  🔎 [{outcome.name}] {outcome.status} - {outcome.detail}")
        self._aggregate(rep)

    # ── 一款 app 全部 case 跑完：跑 app 级 checker（服务端批量回查），回填 ──
    def on_app_finished(self, app: str, case_reports: list) -> None:
        for c in self.app_checkers:
            try:
                results = c.check_app(app, case_reports)
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️ app checker {c.name} 异常（忽略）：{e}")
                results = {rep.id: CheckOutcome(c.name, "inconclusive",
                                                f"app 级回查异常：{e}")
                           for rep in case_reports}
            for rep in case_reports:
                outcome = results.get(rep.id) or CheckOutcome(
                    c.name, "inconclusive", "无回查结果")
                self._record(rep, outcome)
                print(f"  🔎 [{rep.id}][{outcome.name}] "
                      f"{outcome.status} - {outcome.detail}")
        # app 级结论回填后需要重新聚合各 case
        for rep in case_reports:
            self._aggregate(rep)

    # ── 整个 run 全部 case 跑完：跑 run 级 checker（服务端 event_id 批量回查）──
    def on_run_finished(self, run_report) -> None:
        """所有 case 跑完后统一回查（scope="run"，如 server_event）。

        遍历 run_checkers 调 check_run(run_report)→{case_id: CheckOutcome}，
        异常只降级 inconclusive（硬约束 #6），回填后对每个 rep 重新聚合。
        """
        case_reports = list(getattr(run_report, "cases", []) or [])
        for c in self.run_checkers:
            try:
                results = c.check_run(run_report)
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️ run checker {c.name} 异常（忽略）：{e}")
                results = {rep.id: CheckOutcome(c.name, "inconclusive",
                                                f"run 级回查异常：{e}")
                           for rep in case_reports}
            for rep in case_reports:
                outcome = results.get(rep.id) or CheckOutcome(
                    c.name, "inconclusive", "无回查结果")
                self._record(rep, outcome)
                print(f"  🔎 [{rep.id}][{outcome.name}] "
                      f"{outcome.status} - {outcome.detail}")
        # run 级结论回填后需要重新聚合各 case
        for rep in case_reports:
            self._aggregate(rep)

    def finalize(self, rep) -> None:
        """在没有 case checker 时也生成明确的最终验收状态。"""
        self._aggregate(rep)

    # ── 内部 ──────────────────────────────────────────────────────────
    def _safe_check(self, checker, ctx: CheckContext) -> CheckOutcome:
        try:
            return checker.check(ctx)
        except Exception as e:  # noqa: BLE001
            return CheckOutcome(checker.name, "inconclusive",
                                f"checker 执行异常（忽略）：{e}")

    @staticmethod
    def _record(rep, outcome: CheckOutcome) -> None:
        rep.extras.setdefault("checks", {})[outcome.name] = asdict(outcome)

    def _aggregate(self, rep) -> None:
        """调用纯聚合器并把计算结果应用到报告。"""
        checks = rep.extras.get("checks", {})
        expected_names = [
            c.name for c in [*self.case_checkers, *self.app_checkers,
                             *self.run_checkers]
        ]
        # 策略感知时推断 delivery_outcome（policy=none 不参与聚合，保持零回归）。
        delivery_outcome = self._infer_delivery_outcome(checks)
        rep.delivery_outcome = delivery_outcome
        result = OutcomeAggregator.aggregate(
            execution_status=getattr(rep, "execution_status", rep.status),
            checks=checks,
            expected_names=expected_names,
            existing_issue=rep.issue,
            policy=self.policy,
            delivery_outcome=delivery_outcome,
        )
        rep.status = result.status
        rep.verification_status = result.verification_status
        rep.issue = result.issue

    def _infer_delivery_outcome(self, checks) -> str:
        """从视觉判定推断「文件实际发没发出去」（P0，仅 policy!=none 时有意义）。

        P0 阶段来源为视觉结论：audit 场景视觉「外发成功」可信。
        - visual passed → sent（确认外发成功）
        - visual failed  → blocked（未见外发成功，视作被拦/未发出）
        - 缺失 / inconclusive → unknown（不臆测，交给聚合器按未知处理）
        block 下视觉不可靠，P1 会改由阻断类日志/软件失败提示推断（见 §4.1/§4.5）。
        policy=none 时该值不进聚合，仅作为报告展示，返回空串避免误导。
        """
        if self.policy == "none":
            return ""
        visual = (checks or {}).get("visual") or {}
        status = visual.get("status")
        if status == "passed":
            return "sent"
        if status == "failed":
            return "blocked"
        return "unknown"
