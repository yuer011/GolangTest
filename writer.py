"""ReportWriter：把 RunReport 落到 CSV，并打印按软件/场景的分组汇总。

报告维度对齐 DLP 管理后台「软件 → 场景 → 外发动作 → 结果」：
- CSV：每个 case 一行（软件、场景、外发动作、结果、问题描述、截图...），
  便于导入飞书多维表格 / Excel 归档。
- 控制台汇总：按「软件 → 场景」统计通过率，并给出整体「N 个软件、M 个无问题」。
"""
from __future__ import annotations

import csv
import os
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any, IO

from .schema import CaseReport, RunReport

_CSV_HEADER = [
    "软件", "测试场景", "具体外发动作", "case_id", "平台",
    "最终结论", "预期策略", "执行结果", "外发结果", "DLP验收结论",
    "进程名称", "DLP事件日志", "事件ID",
    "视觉判定", "日志判定", "服务端判定",
    "问题描述", "耗时(ms)", "Token消耗", "测试截图",
]

_STATUS_CN = {
    "passed": "没有发现问题",
    "failed": "有问题",
    "inconclusive": "未判定",
    "error": "执行异常",
    "skipped": "已跳过",
}
_EXECUTION_CN = {
    "passed": "执行成功",
    "failed": "执行失败",
    "error": "执行异常",
    "skipped": "已跳过",
}

# 预期策略（run 参数 policy）与外发结果（delivery_outcome）的中文映射
_POLICY_CN = {
    "none": "未指定",
    "audit": "审计",
    "block": "阻断",
}
_DELIVERY_CN = {
    "sent": "已发出",
    "blocked": "被拦截",
    "unknown": "未知",
    "": "-",
}

# 三路验收单列的中文映射
_CHECK_CN = {
    "passed": "通过",
    "failed": "不通过",
    "inconclusive": "未判定",
    "skipped": "未启用",
}


def _check_cell(rep, name: str) -> str:
    """从 CaseReport.extras['checks'] 取某一路结论，转中文单元格。"""
    o = (getattr(rep, "extras", {}) or {}).get("checks", {}).get(name)
    if not o:
        return _CHECK_CN["skipped"]
    return _CHECK_CN.get(o.get("status", ""), o.get("status", ""))


class ReportWriter:
    def __init__(self, *, out_dir: str | Path = "reports", hooks: list[Any] | None = None):
        self.out_dir = Path(out_dir)
        self.hooks = hooks or []
        # 增量落盘的文件句柄与 csv writer（open_incremental 后有效）
        self._inc_file: IO | None = None
        self._inc_writer: Any = None
        self._inc_path: Path | None = None

    @staticmethod
    def _row(c: CaseReport) -> list:
        return [
            c.app or "-",
            c.scenario or "-",
            c.action or "-",
            c.id,
            c.platform,
            _STATUS_CN.get(c.status, c.status),
            _POLICY_CN.get(c.expected_policy or "none", c.expected_policy),
            _EXECUTION_CN.get(c.execution_status, c.execution_status),
            _DELIVERY_CN.get(c.delivery_outcome or "", c.delivery_outcome),
            _CHECK_CN.get(c.verification_status, c.verification_status),
            c.dlp_process_name or "",
            c.dlp_event_log or "",
            c.event_id or "",
            _check_cell(c, "visual"),
            _check_cell(c, "dlp_log"),
            _check_cell(c, "server_event"),
            c.issue or "",
            c.duration_ms,
            c.total_tokens,
            c.screenshot or "",
        ]

    # ── 增量落盘（边跑边写，强杀也保留已完成 case）───────────────────
    def open_incremental(self, run_id: str) -> Path:
        """开一个 CSV 并写好表头，返回文件路径。之后每个 case 调 append_case。"""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._inc_path = self.out_dir / f"{run_id}.csv"
        self._inc_file = self._inc_path.open("x", newline="", encoding="utf-8-sig")
        self._inc_writer = csv.writer(self._inc_file)
        self._inc_writer.writerow(_CSV_HEADER)
        self._inc_file.flush()
        return self._inc_path

    def append_case(self, case: CaseReport) -> None:
        """追加一行并 flush，保证进程被强杀时该行已落盘。"""
        if self._inc_writer is None:
            return
        self._inc_writer.writerow(self._row(case))
        self._inc_file.flush()

    def close_incremental(self) -> Path | None:
        if self._inc_file is not None:
            self._inc_file.close()
            self._inc_file = None
            self._inc_writer = None
        return self._inc_path

    # ── 一次性落盘（保留兼容；增量已开启时无需再调用）───────────────
    def write(self, report: RunReport) -> Path:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / f"{report.run_id}.csv"
        tmp = self.out_dir / f".{path.name}.{uuid.uuid4().hex}.tmp"
        try:
            with tmp.open("x", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(_CSV_HEADER)
                for c in report.cases:
                    writer.writerow(self._row(c))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                tmp.unlink()
        return path

    def fire_hooks(self, report: RunReport) -> None:
        for hook in self.hooks:
            try:
                hook.on_report(report)
            except Exception as e:  # noqa: BLE001
                print(f"[report] hook {getattr(hook, 'name', hook)} 失败：{e}")

    # ── 控制台分组汇总 ──────────────────────────────────────────────
    def print_summary(self, report: RunReport) -> None:
        groups = self._group_by_app(report.cases)

        print("\n========== 测试报告 ==========")
        clean_apps = 0
        for app, scenarios in groups.items():
            app_total = sum(len(v) for v in scenarios.values())
            app_passed = sum(
                c.status == "passed" for v in scenarios.values() for c in v)
            app_ok = app_passed == app_total
            clean_apps += app_ok
            flag = "✅" if app_ok else "⚠️"
            print(f"\n{flag} 软件【{app or '未分类'}】 "
                  f"通过 {app_passed}/{app_total}（{_pct(app_passed, app_total)}）")
            for scenario, cases in scenarios.items():
                passed = sum(c.status == "passed" for c in cases)
                print(f"    · 场景「{scenario or '未分类'}」 "
                      f"{passed}/{len(cases)}（{_pct(passed, len(cases))}）")
                for c in cases:
                    if c.status != "passed":
                        mark = "✗"
                        detail = f"  → {c.issue}" if c.issue else ""
                        print(f"        {mark} {c.action or c.name}"
                              f"[{_STATUS_CN.get(c.status, c.status)}]{detail}")

        app_count = len(groups)
        print(f"\n----- 整体 ----- 共 {app_count} 个软件，"
              f"{clean_apps} 个无问题，{app_count - clean_apps} 个存在问题")
        print(f"用例：total={report.total} passed={report.passed} "
              f"failed={report.failed} inconclusive={report.inconclusive} "
              f"skipped={report.skipped} "
              f"error={report.errored}")

    @staticmethod
    def _group_by_app(cases: list[CaseReport]) -> "OrderedDict[str, OrderedDict[str, list[CaseReport]]]":
        groups: "OrderedDict[str, OrderedDict[str, list[CaseReport]]]" = OrderedDict()
        for c in cases:
            groups.setdefault(c.app, OrderedDict()).setdefault(c.scenario, []).append(c)
        return groups


def _pct(n: int, total: int) -> str:
    return f"{(100.0 * n / total):.0f}%" if total else "0%"
