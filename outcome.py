"""验收结论的统一数据结构与上下文。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

# passed/failed 是确定结论；inconclusive=无法判定（如未配置、查不到、超时）；
# skipped=该路未启用。控制面聚合时，inconclusive/skipped 不会误判为通过。
CheckStatus = Literal["passed", "failed", "inconclusive", "skipped"]


@dataclass
class CheckOutcome:
    """单路验收对某个 case 的结论（报告里各占一列）。"""
    name: str                       # 判定路名：visual / dlp_log / server_event
    status: CheckStatus
    detail: str = ""                # 人读摘要（通过/失败/未判定原因）
    evidence: dict[str, Any] = field(default_factory=dict)  # 命中行/事件 id 等佐证

    @property
    def is_conclusive(self) -> bool:
        return self.status in ("passed", "failed")


@dataclass
class CheckContext:
    """跑一路 checker 需要的上下文，由 runner/manager 填充。"""
    case: Any                       # CaseSpec
    rep: Any                        # CaseReport（可读已执行结果/末步截图路径）
    settings: Any = None
    screen: Any = None              # 需要截图的 checker 用（如视觉复核）
    agent: Any = None
    # 本次运行声明的预期策略（none/audit/block），由 VerificationManager 在
    # on_case_start 注入；checker 据此选用对应类型的日志特征。runner 不感知策略。
    policy: str = "none"
    # 【已废弃/保留字段】旧「多字段指纹」年代由 hard step 收集预期事件、供 app 级
    # 指纹全等匹配用（record_expected_event）。CHG-004 起服务端回查改用 event_id 精确
    # 匹配（见 rep.event_id / server_event.check_run），本字段已无写入方，仅为兼容保留。
    expected_events: list[dict[str, Any]] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)


class CaseChecker(Protocol):
    """一路验收的统一接口。

    - name：判定路名，落报告的列名。
    - scope："case"=每个 case 跑完即判（钩子 on_case_finished）；
      "app"=单款软件全部 case 跑完批量判（钩子 on_app_finished，当前无使用者、保留扩展位）；
      "run"=整个 run 全部 case 跑完统一判（钩子 on_run_finished，服务端 event_id 回查用）。
    """
    name: str
    scope: str

    def check(self, ctx: CheckContext) -> CheckOutcome:  # pragma: no cover
        ...
