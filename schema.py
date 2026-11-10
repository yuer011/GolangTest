"""报告数据结构（dataclass，可直接 json.dumps）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

StepStatus = Literal["passed", "failed", "skipped", "error"]
ExecutionStatus = Literal["passed", "failed", "skipped", "error"]
VerificationStatus = Literal["passed", "failed", "inconclusive", "skipped"]
CaseStatus = Literal["passed", "failed", "inconclusive", "skipped", "error"]


@dataclass
class StepReport:
    name: str
    kind: str
    status: StepStatus
    started_at: str = ""
    finished_at: str = ""
    duration_ms: int = 0
    error: Optional[str] = None
    screenshot: Optional[str] = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseReport:
    id: str
    name: str
    channel: str
    platform: str
    app: str = ""             # 目标软件（报告聚合维度）
    scenario: str = ""        # 测试场景
    action: str = ""          # 具体外发动作
    tags: list[str] = field(default_factory=list)
    # execution_status 只描述自动化动作是否完成（P0 后收窄为「机械动作是否做完」）；
    # verification_status 只描述 DLP 日志/服务端等控制面验收；status 是聚合后最终结论。
    execution_status: ExecutionStatus = "passed"
    verification_status: VerificationStatus = "skipped"
    status: CaseStatus = "inconclusive"
    # 策略断言维度（P0，见 docs/dlp_policy_assertion_design.md §4.1/§5）：
    # expected_policy 为本次运行声明的预期策略（none/audit/block，由 runner 注入）；
    # delivery_outcome 只回答「文件实际发出去了没有」（sent/blocked/unknown），与
    # execution_status 解耦。二者默认空，policy=none（不传 --policy）时完全不参与聚合。
    expected_policy: str = ""
    delivery_outcome: str = ""
    started_at: str = ""
    finished_at: str = ""
    duration_ms: int = 0
    # 本 case 消耗的 LLM token（在 run_one 边界对 provider 全局累计值取差值得到）。
    # 数据层四个值都存；CSV 当前只展示 total_tokens，需要时再加列即可。
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    llm_calls: int = 0
    steps: list[StepReport] = field(default_factory=list)
    error: Optional[str] = None
    issue: str = ""           # 问题描述（失败/异常时人读摘要）
    screenshot: Optional[str] = None   # 代表性截图（末步）
    # 敏感文件名称：文件操作类 case（拖拽/上传/复制粘贴）本次实际外发的文件名，
    # 供报告/多维表格展示并与 DLP 日志按文件名对账；截图类等不涉及文件的 case 留空。
    sensitive_file: str = ""
    # DLP 客户端日志验证命中的字段（仅 policy!=none 且命中本次外发事件时有值）：
    # dlp_process_name = 事件行里的 process name（如 QQ.exe）；
    # dlp_event_log = 整条命中的原始事件日志行（含事件UUID，供人工复核/追溯）。
    dlp_process_name: str = ""
    dlp_event_log: str = ""
    # 本次外发事件在服务端可回查的唯一 id（= 本地 DLP 日志解析出的事件 UUID）。
    # 仅 policy≠none 且本地日志命中时有值；供 run 级服务端回查按之精确查询、并落进 CSV。
    # 平台无关：Windows/Mac 后端命中后都回填此字段，服务端回查只认它、不感知平台。
    event_id: str = ""
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunReport:
    run_id: str
    started_at: str = ""
    finished_at: str = ""
    platform: str = ""
    total: int = 0
    passed: int = 0
    failed: int = 0
    inconclusive: int = 0
    skipped: int = 0
    errored: int = 0
    cases: list[CaseReport] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)
