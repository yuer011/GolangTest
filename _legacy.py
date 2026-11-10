"""块②「明文特征匹配」历史后端（保留兼容）。

本文件是 dlp_log 拆包前 `DlpLogChecker` 的**原样保留**：按「字节偏移增量 + contains/regex
特征匹配（可分 audit/block 类型）」在**明文**日志上判定。它对应两类场景：

1. 当前平台配置里**没有** corplink 解密器（`decoder`）时——回退到「明文按特征匹配」，
   与拆包前行为逐字节一致（零回归）。
2. 单元测试直接构造它验证分型/回退语义（见 tests/test_p0_guards.py 的 LogPolicyTypingTests）。

Windows 上一旦配置了 `decoder`，工厂会改用 `_windows.WindowsCorplinkBackend`
（解密加密日志 + 真实事件解析），本文件不再参与——见 docs/dlp_client_log_verify_design.md。

思路（严格遵守项目「零猜测」硬约束）：
- DLP 客户端日志的**路径与匹配特征都不臆测**，全部来自配置：
    verify.dlp_log.path            日志文件路径；支持两种写法：
        - 字符串：单一路径（两端共用，一般不推荐）
        - 映射：{mac: <mac路径>, windows: <win路径>}，按当前平台自动取用
    verify.dlp_log.default_contains / default_regex   默认期望特征
    verify.dlp_log.cases.<case_id>.contains / .regex  某 case 专属特征（优先）
- 判定窗口用**字节偏移**而非时间戳：case 开始时记录日志文件当前大小，
  检索时只读「本 case 执行期间新追加的内容」，与日志格式无关，天然按时间窗过滤。
- 语义：期望特征出现 = DLP 捕获到该外发事件 = passed；未出现 = DLP 未记录 = failed。
  未配置路径/特征、或文件不存在 = inconclusive（不拉低 case，仅提示补配置）。
"""
from __future__ import annotations

import re
from pathlib import Path

from dlp_auto.core.platform import CURRENT

from ..outcome import CheckContext, CheckOutcome


def resolve_platform_path(path_cfg) -> str | None:
    """把 verify.dlp_log.path 解析成当前平台的路径。

    - str  → 直接用（两端共用）
    - dict → 按当前平台取 path[<platform>]，取不到返回 None（记 inconclusive）
    """
    if path_cfg is None:
        return None
    if isinstance(path_cfg, str):
        return path_cfg or None
    if isinstance(path_cfg, dict):
        return path_cfg.get(CURRENT.value) or None
    return None


class DlpLogChecker:
    name = "dlp_log"
    scope = "case"

    def __init__(self, *, path: str | None,
                 default_contains: str | None = None,
                 default_regex: str | None = None,
                 default_audit_contains: str | None = None,
                 default_audit_regex: str | None = None,
                 default_block_contains: str | None = None,
                 default_block_regex: str | None = None,
                 cases: dict | None = None,
                 raw_path_cfg=None):
        self.path = Path(path).expanduser() if path else None
        self.default_contains = default_contains
        self.default_regex = default_regex
        # 按策略类型分特征（可选，见设计稿 §4.6）；只配通用 contains/regex 时留空。
        self.default_audit_contains = default_audit_contains
        self.default_audit_regex = default_audit_regex
        self.default_block_contains = default_block_contains
        self.default_block_regex = default_block_regex
        self.cases = cases or {}
        # 保留原始配置，便于在未命中当前平台时给出精准提示
        self.raw_path_cfg = raw_path_cfg

    # case 开始时记录日志文件当前大小，作为本 case 的检索起点（字节偏移）
    def on_case_start(self, ctx: CheckContext) -> None:
        if self.path and self.path.exists():
            try:
                ctx.extras["dlp_log_start_offset"] = self.path.stat().st_size
            except OSError:
                ctx.extras["dlp_log_start_offset"] = 0
        else:
            ctx.extras["dlp_log_start_offset"] = 0

    def _features_for(self, spec: dict, kind: str) -> tuple[str | None, str | None]:
        """取某类型特征的 (contains, regex)。

        kind="" 取通用 contains/regex；kind="audit"/"block" 取对应分型特征。
        case 级优先，回落 default_*。
        """
        if kind == "":
            return (spec.get("contains", self.default_contains),
                    spec.get("regex", self.default_regex))
        contains = spec.get(f"{kind}_contains",
                            getattr(self, f"default_{kind}_contains"))
        regex = spec.get(f"{kind}_regex",
                         getattr(self, f"default_{kind}_regex"))
        return contains, regex

    def _has_typed_features(self, spec: dict) -> bool:
        """该 case 是否配置了任一分型特征（audit_* 或 block_*）。"""
        for kind in ("audit", "block"):
            c, r = self._features_for(spec, kind)
            if c or r:
                return True
        return False

    def _read_window(self, ctx: CheckContext):
        """读取本 case 执行期间新增的日志字节窗口。

        返回 (window_text, start_offset, None) 或 (None, start, 提前返回的 CheckOutcome)。
        """
        if not self.path.exists():
            return None, 0, CheckOutcome(
                self.name, "inconclusive",
                f"DLP 日志文件不存在：{self.path}", {"path": str(self.path)})
        start = int(ctx.extras.get("dlp_log_start_offset", 0))
        try:
            with self.path.open("r", encoding="utf-8", errors="replace") as f:
                f.seek(start)
                return f.read(), start, None
        except OSError as e:
            return None, start, CheckOutcome(
                self.name, "inconclusive",
                f"读取 DLP 日志失败：{e}", {"path": str(self.path)})

    def check(self, ctx: CheckContext) -> CheckOutcome:
        if self.path is None:
            # 区分「完全没配」与「配了但当前平台缺路径」两种情况，提示更精准
            if isinstance(self.raw_path_cfg, dict):
                return CheckOutcome(
                    self.name, "inconclusive",
                    f"verify.dlp_log.path 未提供当前平台（{CURRENT.value}）的日志路径。"
                    f"请补 verify.dlp_log.path.{CURRENT.value}。")
            return CheckOutcome(
                self.name, "inconclusive",
                "未配置 DLP 日志路径，无法检索。请在 config 设置 "
                "verify.dlp_log.path（可用 {mac: ..., windows: ...} 按平台区分）"
                "及期望特征 default_contains/default_regex。")

        spec = self.cases.get(ctx.case.id, {})
        policy = getattr(ctx, "policy", "none") or "none"
        # 分型模式：policy 已声明（audit/block）且配置了任一分型特征。
        # 否则走通用特征（policy=none 即零回归；policy!=none 但只配通用为兼容模式）。
        if policy in ("audit", "block") and self._has_typed_features(spec):
            return self._check_typed(ctx, spec, policy)
        return self._check_generic(ctx, spec, policy)

    def _check_generic(self, ctx: CheckContext, spec: dict,
                       policy: str) -> CheckOutcome:
        """通用/兼容模式：只按 contains/regex 匹配（不区分策略类型）。

        - policy=none：完全等价历史行为，evidence 不含 hit_policy_type（零回归）。
        - policy=audit/block 但只配了通用特征：兼容模式，命中记 hit_policy_type=unknown。
        """
        contains, regex = self._features_for(spec, "")
        if not contains and not regex:
            return CheckOutcome(
                self.name, "inconclusive",
                f"case「{ctx.case.id}」未配置期望日志特征（contains/regex），跳过判定。")
        window, start, err = self._read_window(ctx)
        if err:
            return err
        matched, hit = self._match(window, contains, regex)
        expect_desc = regex or contains
        if matched:
            evidence = {"path": str(self.path), "hit_line": hit,
                        "start_offset": start}
            if policy != "none":
                evidence["hit_policy_type"] = "unknown"  # 兼容模式：命中即可
            return CheckOutcome(
                self.name, "passed",
                f"DLP 日志命中期望特征：{expect_desc}", evidence)
        return CheckOutcome(
            self.name, "failed",
            f"DLP 日志未出现期望特征：{expect_desc}（本 case 执行期间新增日志中未匹配）",
            {"path": str(self.path), "start_offset": start})

    def _check_typed(self, ctx: CheckContext, spec: dict,
                     policy: str) -> CheckOutcome:
        """分型模式：区分命中当前策略 / 命中另一策略（错配）/ 未命中。

        当前策略特征缺失时判 inconclusive——绝不回退通用特征假通过（见设计稿 §4.6）。
        """
        cur_contains, cur_regex = self._features_for(spec, policy)
        if not cur_contains and not cur_regex:
            return CheckOutcome(
                self.name, "inconclusive",
                f"case「{ctx.case.id}」已启用分型日志特征，但缺少当前策略"
                f"（{policy}）的特征（{policy}_contains/{policy}_regex）。请补配置，"
                f"不回退通用特征以免误判通过。")
        other = "block" if policy == "audit" else "audit"
        other_contains, other_regex = self._features_for(spec, other)

        window, start, err = self._read_window(ctx)
        if err:
            return err

        cur_matched, cur_hit = self._match(window, cur_contains, cur_regex)
        if cur_matched:
            return CheckOutcome(
                self.name, "passed",
                f"DLP 日志命中当前策略（{policy}）特征：{cur_regex or cur_contains}",
                {"path": str(self.path), "hit_line": cur_hit,
                 "start_offset": start, "hit_policy_type": policy})

        other_matched, other_hit = self._match(window, other_contains, other_regex)
        if other_matched:
            return CheckOutcome(
                self.name, "failed",
                f"DLP 日志命中的是「{other}」类特征，与预期策略「{policy}」不符"
                f"（后台实际策略可能配置错位）。",
                {"path": str(self.path), "hit_line": other_hit,
                 "start_offset": start, "hit_policy_type": other})

        # 未命中任何分型特征：语义随策略而定，把「类型对错」的判断定死在 checker，
        # 聚合器只看统一 status（见 architecture_review_notes「聚合器不应读 hit_policy_type」）。
        # - audit：应留下审计日志却没有 → 审计失效，判 failed。
        # - block：无阻断日志这一铁证，不足以判「已拦截」，也不冤枉判失败 →
        #   inconclusive（设计稿 §4.3 情况一），交由聚合器结合 delivery 收敛。
        if policy == "block":
            return CheckOutcome(
                self.name, "inconclusive",
                f"DLP 日志未出现阻断类特征：{cur_regex or cur_contains}"
                f"（本 case 执行期间新增日志中未匹配），缺阻断铁证，不下确定结论。",
                {"path": str(self.path), "start_offset": start,
                 "hit_policy_type": None})
        return CheckOutcome(
            self.name, "failed",
            f"DLP 日志未出现当前策略（{policy}）期望特征"
            f"：{cur_regex or cur_contains}（本 case 执行期间新增日志中未匹配）",
            {"path": str(self.path), "start_offset": start,
             "hit_policy_type": None})

    @staticmethod
    def _match(text: str, contains: str | None, regex: str | None):
        """任一命中即算命中；返回 (是否命中, 命中的行)。"""
        for line in text.splitlines():
            if contains and contains in line:
                return True, line.strip()[:200]
            if regex and re.search(regex, line):
                return True, line.strip()[:200]
        return False, None


def build_legacy_checker(settings) -> DlpLogChecker:
    """从 verify.dlp_log.* 装配「明文特征匹配」历史 checker（回退/测试用）。"""
    raw_path = settings.get("verify", "dlp_log", "path", default=None)

    def _cfg(key):
        return settings.get("verify", "dlp_log", key, default=None)

    return DlpLogChecker(
        path=resolve_platform_path(raw_path),
        default_contains=_cfg("default_contains"),
        default_regex=_cfg("default_regex"),
        default_audit_contains=_cfg("default_audit_contains"),
        default_audit_regex=_cfg("default_audit_regex"),
        default_block_contains=_cfg("default_block_contains"),
        default_block_regex=_cfg("default_block_regex"),
        cases=settings.get("verify", "dlp_log", "cases", default={}) or {},
        raw_path_cfg=raw_path,
    )
