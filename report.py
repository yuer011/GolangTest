"""回归执行结果模型与本地 JSONL/JSON/HTML 报告。"""

from __future__ import annotations

import html
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

AssertionStatus = Literal["passed", "failed", "inconclusive", "skipped"]
ExecutionStatus = Literal["passed", "failed", "error", "skipped"]
ResultStatus = Literal["passed", "failed", "inconclusive", "error", "skipped"]


@dataclass
class AssertionResult:
    name: str
    checker: str
    status: AssertionStatus
    detail: str
    evidence_ref: str = ""
    screenshot: str = ""


@dataclass
class SourceResult:
    source_ref: str
    status: AssertionStatus
    required_assertions: list[str] = field(default_factory=list)


@dataclass
class RegressionCaseResult:
    id: str
    name: str
    platform: str
    execution_status: ExecutionStatus = "passed"
    status: ResultStatus = "inconclusive"
    issue: str = ""
    error: str = ""
    started_at: str = ""
    finished_at: str = ""
    duration_ms: int = 0
    policy_name: str = ""
    assertions: list[AssertionResult] = field(default_factory=list)
    source_checks: list[SourceResult] = field(default_factory=list)


@dataclass
class RegressionRunResult:
    run_id: str
    platform: str
    started_at: str
    finished_at: str = ""
    cases: list[RegressionCaseResult] = field(default_factory=list)


class RegressionReportWriter:
    def __init__(self, run_dir: str | Path):
        self.run_dir = Path(run_dir)
        self.results_path = self.run_dir / "results.jsonl"
        self.summary_path = self.run_dir / "summary.json"
        self.html_path = self.run_dir / "report.html"
        self.screenshot_dir = self.run_dir / "screenshots"
        self._results_file = None

    def open(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.screenshot_dir.mkdir(exist_ok=True)
        self._results_file = self.results_path.open("x", encoding="utf-8")

    def append_case(self, result: RegressionCaseResult) -> None:
        if self._results_file is None:
            raise RuntimeError("回归报告尚未打开")
        self._results_file.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")
        self._results_file.flush()
        os.fsync(self._results_file.fileno())

    def close(self) -> None:
        if self._results_file is not None:
            self._results_file.close()
            self._results_file = None

    def write_final(self, result: RegressionRunResult) -> None:
        payload = asdict(result)
        with self.summary_path.open("x", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False, indent=2))
        with self.html_path.open("x", encoding="utf-8") as file:
            file.write(self._render_html(result))

    @staticmethod
    def _render_html(result: RegressionRunResult) -> str:
        rows: list[str] = []
        for case in result.cases:
            sources = "<br>".join(
                f"{html.escape(item.source_ref)}: <strong>{html.escape(item.status)}</strong>"
                for item in case.source_checks
            )
            assertions = "<br>".join(
                f"{html.escape(item.name)}: "
                f"<strong>{html.escape(item.status)}</strong> "
                f"{html.escape(item.detail)}"
                for item in case.assertions
            )
            rows.append(
                "<tr>"
                f"<td>{html.escape(case.id)}</td>"
                f"<td>{html.escape(case.execution_status)}</td>"
                f"<td>{html.escape(case.status)}</td>"
                f"<td>{sources}</td>"
                f"<td>{assertions}</td>"
                f"<td>{html.escape(case.issue)}</td>"
                "</tr>"
            )
        body = "\n".join(rows)
        return (
            '<!doctype html><html lang="zh-CN"><head>'
            '<meta charset="utf-8"><title>DLP 回归报告</title>'
            "<style>body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;"
            "margin:24px;color:#202124}table{border-collapse:collapse;width:100%}"
            "th,td{border:1px solid #dadce0;padding:8px;text-align:left;"
            "vertical-align:top}th{background:#f5f6f7}</style></head><body>"
            f"<h1>DLP 回归报告</h1><p>run_id: {html.escape(result.run_id)}"
            f"<br>platform: {html.escape(result.platform)}</p>"
            "<table><thead><tr><th>Case</th><th>执行</th><th>结论</th>"
            "<th>原回归映射</th><th>断言</th><th>问题</th></tr></thead>"
            f"<tbody>{body}</tbody></table></body></html>"
        )
