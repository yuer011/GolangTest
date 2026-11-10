"""执行结果与控制面验收结果的纯聚合逻辑。

策略感知（P0，见 docs/dlp_policy_assertion_design.md §4）：
- ``policy="none"``（默认，不传 --policy）：走历史分支，行为与引入本能力前**逐字节一致**。
- ``policy="audit"``：消费 ``delivery_outcome``（文件实际发没发出去）+ 控制面日志做交叉验证。
- ``policy="block"``：``delivery_outcome`` × 阻断日志交叉验证——已发出=阻断失效判 failed（日志
  无翻案权）；已拦截再看阻断日志 AND 门；外发结果未知则 inconclusive。
聚合器保持纯粹：只根据显式入参计算，不读取或修改 CaseReport。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class AggregationResult:
    status: str
    verification_status: str
    issue: str


class OutcomeAggregator:
    """只根据显式输入计算最终结论，不读取或修改 CaseReport。"""

    @staticmethod
    def aggregate(
        *,
        execution_status: str,
        checks: Mapping[str, Mapping[str, Any]],
        expected_names: Sequence[str],
        existing_issue: str = "",
        policy: str = "none",
        delivery_outcome: str = "",
    ) -> AggregationResult:
        # policy=none 是零回归分支：定义等于引入策略断言前的原始逻辑。
        if policy == "audit":
            return OutcomeAggregator._aggregate_audit(
                execution_status=execution_status,
                delivery_outcome=delivery_outcome,
                checks=checks,
                expected_names=expected_names,
                existing_issue=existing_issue,
            )
        if policy == "block":
            return OutcomeAggregator._aggregate_block(
                execution_status=execution_status,
                delivery_outcome=delivery_outcome,
                checks=checks,
                expected_names=expected_names,
                existing_issue=existing_issue,
            )
        return OutcomeAggregator._aggregate_none(
            execution_status=execution_status,
            checks=checks,
            expected_names=expected_names,
            existing_issue=existing_issue,
        )

    # ── policy=none：历史逻辑（保持逐字节等价，零回归）──────────────────
    @staticmethod
    def _aggregate_none(
        *,
        execution_status: str,
        checks: Mapping[str, Mapping[str, Any]],
        expected_names: Sequence[str],
        existing_issue: str,
    ) -> AggregationResult:
        # 唯一聚合语义：所有「已启用（进 expected_names）」的控制面 checker 都
        # 必须 passed 才算通过。「可有可无 / 未实装」的验收路以「不注册、不进
        # expected_names」来表达，而非返回假 pass——无证据不生成通过结论。
        if execution_status in ("error", "skipped", "failed"):
            return AggregationResult(
                status=execution_status,
                verification_status="skipped",
                issue=existing_issue,
            )
        return OutcomeAggregator._aggregate_checks(
            checks=checks,
            expected_names=expected_names,
            existing_issue=existing_issue,
        )

    # ── policy=audit：delivery_outcome × 日志 交叉验证（§4.3 audit 行）──
    @staticmethod
    def _aggregate_audit(
        *,
        execution_status: str,
        delivery_outcome: str,
        checks: Mapping[str, Mapping[str, Any]],
        expected_names: Sequence[str],
        existing_issue: str,
    ) -> AggregationResult:
        # 执行异常/跳过/失败都必须短路：中间视觉通过或 DLP 日志命中不能把
        # 「后续步骤明确失败」翻案成 passed（硬约束：执行成功 ≠ DLP 有效）。
        if execution_status in ("error", "skipped", "failed"):
            return AggregationResult(
                status=execution_status,
                verification_status="skipped",
                issue=existing_issue,
            )
        # 审计策略下文件被拦截 → 与预期（应外发成功）不符，判 failed。
        if delivery_outcome == "blocked":
            return AggregationResult(
                status="failed",
                verification_status="failed",
                issue=existing_issue
                or "审计策略下文件被拦截（外发结果=被拦截），与预期外发成功不符。",
            )
        # delivery 未知：无法确认外发结果，不下结论。
        if delivery_outcome != "sent":
            return AggregationResult(
                status="inconclusive",
                verification_status="inconclusive",
                issue=existing_issue
                or "无法确认文件是否发出（外发结果=未知），不下确定结论。",
            )
        # delivery=sent：文件确已发出，再与控制面日志做「全过才通过」AND 门交叉验证。
        return OutcomeAggregator._aggregate_checks(
            checks=checks,
            expected_names=expected_names,
            existing_issue=existing_issue,
        )

    # ── policy=block：delivery_outcome × 阻断日志 交叉验证（§4.3 block 行）──
    @staticmethod
    def _aggregate_block(
        *,
        execution_status: str,
        delivery_outcome: str,
        checks: Mapping[str, Mapping[str, Any]],
        expected_names: Sequence[str],
        existing_issue: str,
    ) -> AggregationResult:
        # 执行失败同样不能被「疑似已拦截 + 阻断日志」翻案成通过。
        if execution_status in ("error", "skipped", "failed"):
            return AggregationResult(
                status=execution_status,
                verification_status="skipped",
                issue=existing_issue,
            )
        # 情况二：文件竟然发出去了 = 阻断失效 = 泄露。日志无翻案权（哪怕留了阻断日志，
        # 文件已外发就是失败），故不看 checks，直接 failed（设计稿 §4.3 情况二）。
        if delivery_outcome == "sent":
            return AggregationResult(
                status="failed",
                verification_status="failed",
                issue=existing_issue
                or "阻断策略下文件仍被发出（外发结果=已发出），阻断失效，判失败。",
            )
        # delivery 未确认（非 blocked）：连拦没拦住都不知道，不下确定结论。
        if delivery_outcome != "blocked":
            return AggregationResult(
                status="inconclusive",
                verification_status="inconclusive",
                issue=existing_issue
                or "无法确认文件是否被拦截（外发结果=未知），不下确定结论。",
            )
        # delivery=blocked：疑似已拦截，再与阻断日志做 AND 门交叉验证。
        # checker 已把「命中阻断类=passed / 命中审计类=failed / 未命中=inconclusive」
        # 定死在 status 里，聚合器只需沿用统一 AND 门，无需读 hit_policy_type。
        return OutcomeAggregator._aggregate_checks(
            checks=checks,
            expected_names=expected_names,
            existing_issue=existing_issue,
        )

    # ── 控制面日志「全过才通过」AND 门（none 与 audit-sent 共用）─────────
    @staticmethod
    def _aggregate_checks(
        *,
        checks: Mapping[str, Mapping[str, Any]],
        expected_names: Sequence[str],
        existing_issue: str,
    ) -> AggregationResult:
        if not expected_names:
            return AggregationResult(
                status="inconclusive",
                verification_status="skipped",
                issue=existing_issue
                or "自动化动作执行成功，但未启用 DLP 日志或服务端验收。",
            )

        outcomes = [checks.get(name) for name in expected_names]
        failed = [
            (name, checks[name])
            for name in expected_names
            if checks.get(name, {}).get("status") == "failed"
        ]
        all_passed = all(
            outcome and outcome.get("status") == "passed"
            for outcome in outcomes
        )

        if failed:
            verification_status = status = "failed"
        elif all_passed:
            verification_status = status = "passed"
        else:
            verification_status = status = "inconclusive"

        issue = existing_issue
        if failed:
            issue = "；".join(
                f"[{name}] {outcome.get('detail', '')}"
                for name, outcome in failed
            )
        elif status == "passed":
            # 全过即无问题可述：显式清空可能遗留的旧 issue。
            # 关键于 run 级回查（server_event 由 inconclusive 翻成 passed）后重新聚合——
            # 首次聚合写下的「未形成确定结论」若不清，passed 的 case 会带着矛盾描述
            # （见 CHG-004 真机联调：拖拽事件补查命中后 status=passed 但 issue 残留）。
            issue = ""
        elif status == "inconclusive":
            pending = [
                f"{name}={checks.get(name, {}).get('status', 'missing')}"
                for name in expected_names
                if checks.get(name, {}).get("status") != "passed"
            ]
            issue = f"DLP 验收未形成确定结论：{', '.join(pending)}"

        return AggregationResult(
            status=status,
            verification_status=verification_status,
            issue=issue,
        )
