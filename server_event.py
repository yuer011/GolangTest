"""块③：服务端事件上报回查验收（**run 级**，两阶段：登记 event_id → 批量查 → 回填）。

为什么是 run 级、全部跑完统一查（详见 docs/archive/server_event_requery_design.md，已归档）：
DLP 事件上报到服务端有秒~分钟级延迟。等**所有 case 跑完**再统一按 event_id 查，
先跑的 case 那时早已上报完成；只有末尾少数可能还没到，全局最多等一个上报周期补查一次。

    阶段一（执行期，每个 case）：本地日志命中外发事件 → 解析出事件 UUID →
                     由 dlp_log 后端回填到 rep.event_id（见 _windows._fill_report）。
    阶段二（全部 case 跑完，一次）：收集所有 rep.event_id，按 id 批量查服务端：
                     查到 → passed；有没查到的 → 全局等一次 report_delay_sec 再补查一轮；
                     仍没查到 → inconclusive（不臆测、绝不 pass，硬约束 #10）。

event_id 唯一主键：改用本地日志的事件 UUID 精确匹配，**废弃**旧的多字段指纹全等
（file_name/action/device/time）那套脆弱近似匹配（无唯一键、差一秒就错、且登记端从未接线）。

接口：真实 HTTP 封装在 feilian_client.py，本类只在 mock=false 时**懒加载**它并委托
（故 mock 跑通无需装 requests/pycryptodome）。是否 passed/inconclusive 的裁决在本类。

零副作用（硬约束 #6）：登录/查询任何异常都只降级 inconclusive，不打断 run、不 fake pass。
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta

from .outcome import CheckOutcome


class ServerEventChecker:
    name = "server_event"
    scope = "run"

    def __init__(self, *, settings=None, mock: bool = True,
                 report_delay_sec: float = 60.0, query_window_days: int = 1,
                 policy: str = "none"):
        self._settings = settings
        self.mock = mock
        # 某事件首次没查到时，全局等待一次的上报周期（秒）；之后再没查到不再等。
        self.report_delay_sec = float(report_delay_sec)
        # 按 event_id 精确查，start/end 时间窗仅作兜底：run 起止 ± 这么多天。
        self.query_window_days = int(query_window_days)
        # 本次运行的预期策略（none/audit/block）：命中后据此校验服务端记录的处置动作
        # 是否与预期一致（audit 应放行、block 应拦截）。none 不做处置校验（仅命中即过）。
        self.policy = policy or "none"
        self._client = None          # 懒加载的 FeilianClient（登录一次、复用）
        self._waited = False         # 全局「只等一次」标志

    # ── 阶段二：所有 case 跑完后按 event_id 批量回查 ──────────────────
    def check_run(self, run_report) -> dict[str, "CheckOutcome"]:
        """对整个 run 的所有 case 批量查询，返回 {case_id: CheckOutcome}。"""
        case_reports = list(getattr(run_report, "cases", []) or [])
        out: dict[str, CheckOutcome] = {}

        # 收集有 event_id 的 case；无 event_id 的直接 inconclusive（无从回查）。
        id_to_cases: dict[str, list[str]] = {}
        for rep in case_reports:
            eid = (getattr(rep, "event_id", "") or "").strip()
            if not eid:
                out[rep.id] = CheckOutcome(
                    self.name, "inconclusive",
                    "未取得事件ID（本地日志未命中或未启用 --policy），无从做服务端回查。")
                continue
            id_to_cases.setdefault(eid, []).append(rep.id)

        if not id_to_cases:
            return out

        # mock：仅验证链路，恒 inconclusive（守硬约束 #10，绝不产生生产通过结论）。
        if self.mock:
            for eid, cids in id_to_cases.items():
                for cid in cids:
                    out[cid] = CheckOutcome(
                        self.name, "inconclusive",
                        "服务端回查处于 mock 模式，仅验证链路，不产生生产通过结论。",
                        {"mocked": True, "event_id": eid})
            return out

        # 真实回查：查 → 缺的全局等一次 → 补查 → 仍缺记 inconclusive。
        event_ids = list(id_to_cases.keys())
        start, end = self._time_window(run_report)
        try:
            hits = self._query(event_ids, start, end)
        except Exception as e:  # noqa: BLE001  硬约束 #6：异常只降级、不打断 run
            for cids in id_to_cases.values():
                for cid in cids:
                    out[cid] = CheckOutcome(
                        self.name, "inconclusive",
                        f"服务端回查异常（忽略，不打断 run）：{e}")
            return out

        missing = [eid for eid in event_ids if eid not in hits]
        if missing and not self._waited:
            self._waited = True
            print(f"  ⏳ 服务端尚有 {len(missing)}/{len(event_ids)} 个事件未查到，"
                  f"全局等待一次上报周期 {self.report_delay_sec:.0f}s 后补查（只等这一次）…")
            time.sleep(self.report_delay_sec)
            try:
                hits.update(self._query(missing, start, end))
            except Exception as e:  # noqa: BLE001
                print(f"     ⚠️ 补查异常（忽略）：{e}")

        for eid, cids in id_to_cases.items():
            events = hits.get(eid)
            outcome = self._judge_events(eid, events)
            for cid in cids:
                out[cid] = outcome
        return out

    # ── 命中裁决：条数校验 + 处置动作 vs policy 校验 ──────────────────
    def _judge_events(self, event_id: str, events) -> "CheckOutcome":
        """对某 event_id 的查询结果下结论（0 条/多条/处置是否符合预期）。

        规则（用户 2026-08-06 定；真实字段见 docs/archive/server_event_requery_design.md，已归档）：
        - 0 条（未查到）→ inconclusive：可能上报延迟或未上报，不臆测（硬约束 #10）。
        - >1 条 → failed：event_id 是 UUID，本应唯一；多条即异常，原因落表。
        - 恰好 1 条 → 读该事件处置动作，与本次 policy 交叉验证：
            拦截判据 = event_result.intercept 为真；缺失 / 非真 = 放行。
            · policy=block：应拦截 → intercept 真=passed，放行=failed（阻断失效）。
            · policy=audit：应放行 → 放行=passed，被拦截=failed（审计却拦截）。
            · policy=none：不做处置校验，命中即 passed（保持无策略时不加码）。
        """
        if not events:
            return CheckOutcome(
                self.name, "inconclusive",
                f"服务端未查到该事件（event_id={event_id}）：可能上报延迟或未上报，"
                "不臆测（绝不判 pass，硬约束 #10）。",
                {"event_id": event_id})
        if len(events) > 1:
            return CheckOutcome(
                self.name, "failed",
                f"服务端查到 {len(events)} 条同一事件（event_id={event_id}），"
                "事件ID 本应唯一，结果异常。",
                {"event_id": event_id, "count": len(events)})

        ev = events[0]
        intercepted = self._is_intercepted(ev)
        evidence = {"event_id": event_id, "intercepted": intercepted, "hit": ev}
        if self.policy == "block":
            if intercepted:
                return CheckOutcome(
                    self.name, "passed",
                    "服务端已查到本次外发事件，且记录为已拦截，符合阻断预期。",
                    evidence)
            return CheckOutcome(
                self.name, "failed",
                "服务端记录本次外发未被拦截（已放行），与阻断策略预期不符（阻断失效）。",
                evidence)
        if self.policy == "audit":
            if intercepted:
                return CheckOutcome(
                    self.name, "failed",
                    "服务端记录本次外发被拦截，与审计策略预期（应放行）不符。",
                    evidence)
            return CheckOutcome(
                self.name, "passed",
                "服务端已查到本次外发事件，且记录为放行，符合审计预期。",
                evidence)
        # policy=none：不做处置校验，仅以「查到」为通过（无策略时不加码）。
        return CheckOutcome(
            self.name, "passed",
            "服务端已查到本次外发事件。", evidence)

    @staticmethod
    def _is_intercepted(event: dict) -> bool:
        """处置动作判据：event_result.intercept 为真 = 拦截；缺失 / 非真 = 放行。

        取值来自真机样本（audit 事件的 event_result 无 intercept 字段 → 放行）。
        只认布尔真值，取不到一律按放行处理（不臆测、不误报拦截）。
        """
        result = event.get("event_result") if isinstance(event, dict) else None
        if not isinstance(result, dict):
            return False
        return bool(result.get("intercept"))

    # ── 真实查询扩展点（委托 feilian_client；mock/测试可覆写本方法）─────
    def _query(self, event_ids: list[str], start: int, end: int) -> dict[str, list[dict]]:
        """按 event_id 批量查，返回 {event_id: 命中事件列表}（仅含查到真实数据的 id）。

        默认委托 feilian_client；单测可覆写本方法以免依赖网络/requests/pycryptodome。
        """
        client = self._ensure_client()
        return client.query_events(event_ids, start=start, end=end)

    def _ensure_client(self):
        """懒加载并登录一次，之后复用（含首查 + 补查两轮）。"""
        if self._client is None:
            from .feilian_client import build_client
            client = build_client(self._settings)
            client.login()
            self._client = client
        return self._client

    def _time_window(self, run_report) -> tuple[int, int]:
        """由 run 起止时间 ± query_window_days 推导 unix 秒时间窗（缺失回退 now）。"""
        span = timedelta(days=self.query_window_days)

        def _parse(v):
            try:
                return datetime.fromisoformat(v) if v else None
            except (ValueError, TypeError):
                return None

        start_dt = _parse(getattr(run_report, "started_at", None)) or datetime.now()
        end_dt = _parse(getattr(run_report, "finished_at", None)) or datetime.now()
        return int((start_dt - span).timestamp()), int((end_dt + span).timestamp())


def build_server_event_checker(settings, *, policy: str = "none") -> ServerEventChecker:
    return ServerEventChecker(
        settings=settings,
        mock=bool(settings.get("verify", "server", "mock", default=True)),
        report_delay_sec=float(
            settings.get("verify", "server", "report_delay_sec", default=60)),
        query_window_days=int(
            settings.get("verify", "server", "query_window_days", default=1)),
        policy=policy,
    )
