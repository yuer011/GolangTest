"""基于冻结截图的只读 UI 状态断言。"""

from __future__ import annotations

from typing import Any

from dlp_auto.core.judge import Verdict

from ..spec import AssertionSpec, RegressionStepContext, resolve_text


def evaluate_ui_state(
    spec: AssertionSpec,
    ctx: RegressionStepContext,
    *,
    image_b64: str,
    judge: Any,
) -> Verdict:
    if spec.checker != "ui_state":
        raise ValueError(f"ui_state adapter 不支持 checker={spec.checker!r}")
    assertion = resolve_text(spec.assertion_set, ctx).strip()
    if not assertion:
        return Verdict("inconclusive", "UI 断言文本为空")
    return judge.verify_presence(assertion, image_b64)
