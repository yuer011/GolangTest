"""Run 级 DLP 事件审计（疑似误报旁路）——RunEventAuditor。

定位（见 docs/archive/run_dlp_event_audit_design.md）：在一次 run 的时间窗内全量扫描两端 DLP
客户端日志解析出的**全部**真实外发事件，用「预期事件台账」反向筛出没有任何 case 能解释
的事件（疑似误报），单独输出独立产物。

底线（硬约束 #6/#10/#11、AGENTS §1.2/§1.3）：
- **旁路零副作用**：本模块**不注册为 checker**、不进 `expected_names`、不参与 aggregator；
  只读日志 + 写两个独立文件，**绝不**修改任何 case 的 execution/verification/delivery/status，
  也不改退出码。
- **默认关、可整体删除**：由 CaseRunner.auditor 是否为 None 决定；删除本文件 +
  runner 的可选接线后，run 行为与不引入本能力逐字节一致。
- **失败不冒充干净**：collect_events 抛错（配置缺失/解密失败/后端不支持）时，审计状态标
  `inconclusive` 并说明原因，绝不把「没扫完」显示成「没发现问题」。
"""
from __future__ import annotations

import csv
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from .dlp_log._base import DlpEvent, EventCollectError

# 事件四分类：
#   expected        明确归属到某 case 的预期外发事件
#   expected_retry  同一预期的重复事件（同名文件重发 / 截图窗口内多次）
#   ambiguous       边界不清：多窗口同时命中，或落在 step 后的落盘缓冲区无法唯一归属
#   unexpected      无任何预期登记能解释 → 疑似误报
Classification = str

_DEFAULT_IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".bmp", ".gif"]


@dataclass
class _Expectation:
    """一条 step 级预期登记（台账项）。"""
    case_id: str
    kind: str                       # "file" / "image"
    sensitive_file: str             # 文件类：run 级唯一文件名；截图类为空
    started_at: Optional[datetime]  # step 事件发射窗口起点
    finished_at: Optional[datetime]


@dataclass
class _CaseWindow:
    """一个 case 的执行窗口 + 其 checker 命中的事件 UUID（供归类/定位用）。"""
    case_id: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    event_id: str
    sensitive_file: str


@dataclass
class AuditedEvent:
    """一条真实事件的归类结果。"""
    ts: str
    event_uuid: str
    process_name: str
    file_name: str
    origin_file_path: str
    classification: Classification
    reason: str
    explained_by_case: str          # 归属/解释该事件的 case（预期类才有值）
    case_at: str                    # 事件发生时正在执行的 case（按时间窗）
    nearest_case: str               # 时间上最接近的 case
    raw_line: str


@dataclass
class AuditResult:
    """一次审计的汇总结论（旁路，仅落独立产物 + 控制台一行）。"""
    status: str = "completed"       # completed / inconclusive
    reason: str = ""                # inconclusive 时说明原因
    run_started_at: str = ""
    actions_finished_at: str = ""
    event_window_finished_at: str = ""
    run_finished_at: str = ""
    total: int = 0
    expected: int = 0
    expected_retry: int = 0
    ambiguous: int = 0
    unexpected: int = 0
    audit_json_path: str = ""
    unexpected_csv_path: str = ""

    def summary_line(self) -> str:
        if self.status != "completed":
            return f"DLP 事件审计：未完成（{self.reason or '原因未知'}），未生成结论"
        suffix = (f"（详见 {self.unexpected_csv_path}）"
                  if (self.ambiguous + self.unexpected) else "（无疑似误报）")
        return (f"DLP 事件审计：总计 {self.total}，预期 {self.expected}，"
                f"重试 {self.expected_retry}，模糊 {self.ambiguous}，"
                f"预期外 {self.unexpected}{suffix}")


class RunEventAuditor:
    """编排「读预期台账 → 调后端收集事件 → 归类 → 写产物」的旁路诊断器。

    使用方式（由 CaseRunner 在 auditor 非 None 时可选调用；关掉即完全不触碰）：
        auditor.mark_run_started()                 # 首个 case 执行前
        auditor.record_expectation(...)            # 每个被标注的 step 跑完后
        auditor.mark_actions_finished()            # 所有 case + teardown 完成
        result = auditor.finalize_and_write(reps)  # 主报告持久化之后
    """

    def __init__(self, *, context, backend, settle_sec: float = 15.0,
                 image_exts: list[str] | None = None):
        self._context = context
        self._backend = backend
        self._settle_sec = float(settle_sec or 0)
        exts = image_exts or getattr(backend, "image_exts", None) or _DEFAULT_IMAGE_EXTS
        self._image_exts = [str(e).lower() for e in exts]
        # 四个时间点（见设计稿 §3）
        self._run_started_at: Optional[datetime] = None
        self._actions_finished_at: Optional[datetime] = None
        self._event_window_finished_at: Optional[datetime] = None
        # 预期台账（step 级登记）
        self._expectations: list[_Expectation] = []

    # ── 时间边界 ──────────────────────────────────────────────────────
    def mark_run_started(self) -> None:
        self._run_started_at = datetime.now()

    def mark_actions_finished(self) -> None:
        self._actions_finished_at = datetime.now()
        self._event_window_finished_at = (
            self._actions_finished_at + timedelta(seconds=self._settle_sec))

    # ── 预期事件登记（每个被 expect_dlp 标注的 step 跑完后调一次）──────
    def record_expectation(self, *, case_id: str, kind: str,
                           sensitive_file: str,
                           started_at: Optional[datetime],
                           finished_at: Optional[datetime]) -> None:
        self._expectations.append(_Expectation(
            case_id=case_id, kind=str(kind),
            sensitive_file=(sensitive_file or "").strip(),
            started_at=started_at, finished_at=finished_at))

    # ── 收尾：settle → 扫描 → 归类 → 写产物 → 返回汇总 ────────────────
    def finalize_and_write(self, case_reports: list) -> AuditResult:
        """在主报告持久化之后调用。任何异常都被吞成 inconclusive，绝不外泄。"""
        if self._actions_finished_at is None:
            self.mark_actions_finished()
        # 落盘缓冲：等到 event_window_finished_at（若服务端回查已耗时更久则不再等）。
        remaining = (self._event_window_finished_at - datetime.now()).total_seconds()
        if remaining > 0:
            print(f"  ⏳ DLP 事件审计：等待 {remaining:.0f}s 落盘缓冲后扫描窗口内事件")
            time.sleep(remaining)

        self._build_ledger(case_reports)
        result = AuditResult(
            run_started_at=_iso(self._run_started_at),
            actions_finished_at=_iso(self._actions_finished_at),
            event_window_finished_at=_iso(self._event_window_finished_at),
        )

        collect = getattr(self._backend, "collect_events", None)
        if not callable(collect):
            result.status = "inconclusive"
            result.reason = ("当前 DLP 日志后端不支持事件收集（collect_events），"
                             "无法扫描疑似误报（可能未配置解密器/路径）。")
            result.run_finished_at = _iso(datetime.now())
            self._write_products(result, [])
            return result

        try:
            events = collect(self._run_started_at, self._event_window_finished_at)
        except EventCollectError as e:
            result.status = "inconclusive"
            result.reason = str(e)
            result.run_finished_at = _iso(datetime.now())
            self._write_products(result, [])
            return result
        except Exception as e:  # noqa: BLE001  纯诊断：任何后端异常都降级，不外泄
            result.status = "inconclusive"
            result.reason = f"事件扫描异常（已降级）：{e}"
            result.run_finished_at = _iso(datetime.now())
            self._write_products(result, [])
            return result

        audited = self._classify(_dedup_by_uuid(events))
        result.total = len(audited)
        result.expected = sum(a.classification == "expected" for a in audited)
        result.expected_retry = sum(a.classification == "expected_retry" for a in audited)
        result.ambiguous = sum(a.classification == "ambiguous" for a in audited)
        result.unexpected = sum(a.classification == "unexpected" for a in audited)
        result.run_finished_at = _iso(datetime.now())
        self._write_products(result, audited)
        return result

    # ── 台账构建 ──────────────────────────────────────────────────────
    def _build_ledger(self, case_reports: list) -> None:
        """从 case 报告 + step 级登记构建归类所需索引。

        - 文件类归属：以 rep.sensitive_file 为准（run 级唯一、始终可得，无需 step 标注）；
        - 图片类归属：以 step 级登记的截图窗口为准（时间窗归属，必须由工厂标注）；
        - checker 命中 UUID：rep.event_id（case 级日志验收命中的事件 UUID）。
        """
        self._file_case: dict[str, str] = {}
        self._checker_uuids: dict[str, str] = {}
        self._case_windows: list[_CaseWindow] = []
        for rep in case_reports or []:
            cid = getattr(rep, "id", "") or ""
            sf = (getattr(rep, "sensitive_file", "") or "").strip()
            eid = (getattr(rep, "event_id", "") or "").strip()
            if sf:
                self._file_case[sf] = cid
            if eid:
                self._checker_uuids[eid] = cid
            self._case_windows.append(_CaseWindow(
                case_id=cid,
                started_at=_parse(getattr(rep, "started_at", "")),
                finished_at=_parse(getattr(rep, "finished_at", "")),
                event_id=eid, sensitive_file=sf))
        # 图片截图窗口（来自 step 级登记）
        self._image_windows = [
            e for e in self._expectations
            if e.kind == "image" and e.started_at is not None
            and e.finished_at is not None]

    # ── 归类 ──────────────────────────────────────────────────────────
    def _classify(self, events: list[DlpEvent]) -> list[AuditedEvent]:
        audited: list[AuditedEvent] = []
        file_seen: dict[str, int] = {}      # sensitive_file -> 已出现次数
        window_seen: dict[str, int] = {}    # image case_id -> 已出现次数
        for ev in events:
            cls, reason, by_case = self._classify_one(ev, file_seen, window_seen)
            audited.append(AuditedEvent(
                ts=_iso(ev.ts),
                event_uuid=ev.event_uuid,
                process_name=ev.process_name,
                file_name=self._file_name_of(ev),
                origin_file_path=ev.origin_file_path,
                classification=cls, reason=reason,
                explained_by_case=by_case,
                case_at=self._case_at(ev.ts),
                nearest_case=self._nearest_case(ev.ts),
                raw_line=ev.raw_line[:500]))
        return audited

    def _classify_one(self, ev: DlpEvent, file_seen: dict, window_seen: dict):
        # 规则 1：事件 UUID 已被某 case 的 checker 命中 → expected
        if ev.event_uuid and ev.event_uuid in self._checker_uuids:
            cid = self._checker_uuids[ev.event_uuid]
            sf = self._match_file(ev)
            if sf:
                file_seen[sf] = file_seen.get(sf, 0) + 1
            return "expected", f"事件UUID 已被 case「{cid}」的日志验收命中", cid

        # 规则 2/3：唯一文件名与某 case 的外发文件精确匹配（首条 expected、其余 retry）
        sf = self._match_file(ev)
        if sf:
            n = file_seen.get(sf, 0)
            file_seen[sf] = n + 1
            cid = self._file_case.get(sf, "")
            if n == 0:
                return "expected", f"唯一文件名「{sf}」与 case「{cid}」外发文件精确匹配", cid
            return ("expected_retry",
                    f"唯一文件名「{sf}」第 {n + 1} 次出现（case「{cid}」重发/重试）", cid)

        # 规则 4/5：图片事件按截图 step 时间窗归属
        if self._is_image(ev):
            windows = self._windows_containing(ev.ts)
            if len(windows) == 1:
                cid = windows[0].case_id
                n = window_seen.get(cid, 0)
                window_seen[cid] = n + 1
                if n == 0:
                    return "expected", f"图片事件落在 case「{cid}」截图 step 的发射窗口内", cid
                return ("expected_retry",
                        f"图片事件在 case「{cid}」截图窗口内第 {n + 1} 次出现（截图重试）", cid)
            if len(windows) > 1:
                ids = "/".join(w.case_id for w in windows)
                return ("ambiguous",
                        f"图片事件同时落在多个截图窗口内（{ids}），无法唯一归属", "")
            tail = self._window_in_settle_tail(ev.ts)
            if tail is not None:
                return ("ambiguous",
                        f"图片事件落在 case「{tail.case_id}」截图 step 之后的落盘缓冲区，"
                        f"可能是截图重试或延迟落盘，无法唯一归属", tail.case_id)
            return ("unexpected",
                    "图片事件无任何截图 step 预期可解释（疑似误报）", "")

        # 规则 6：没有任何预期登记能解释 → unexpected
        return ("unexpected",
                "无任何预期登记能解释该事件（疑似计划外外发或后台行为）", "")

    # ── 匹配/判定 helper ─────────────────────────────────────────────
    def _match_file(self, ev: DlpEvent) -> str:
        """返回命中的唯一文件名（sensitive_file），无则空串。与后端 _match 同口径。"""
        path = ev.origin_file_path or ""
        leak_name = str(ev.extras.get("leak_file_name") or "") if ev.extras else ""
        for sf in self._file_case:
            if sf and (sf in path or sf == leak_name):
                return sf
        return ""

    def _is_image(self, ev: DlpEvent) -> bool:
        ext = str(ev.extras.get("leak_file_extension") or "").lower() if ev.extras else ""
        if not ext:
            ext = Path(ev.origin_file_path or "").suffix.lower()
        return ext in self._image_exts

    def _file_name_of(self, ev: DlpEvent) -> str:
        if ev.extras and ev.extras.get("leak_file_name"):
            return str(ev.extras["leak_file_name"])
        return Path(ev.origin_file_path or "").name

    def _windows_containing(self, ts: Optional[datetime]) -> list[_Expectation]:
        if ts is None:
            return []
        return [w for w in self._image_windows
                if w.started_at <= ts <= w.finished_at]

    def _window_in_settle_tail(self, ts: Optional[datetime]) -> Optional[_Expectation]:
        if ts is None or self._settle_sec <= 0:
            return None
        buf = timedelta(seconds=self._settle_sec)
        for w in self._image_windows:
            if w.finished_at < ts <= w.finished_at + buf:
                return w
        return None

    def _case_at(self, ts: Optional[datetime]) -> str:
        if ts is None:
            return ""
        for w in self._case_windows:
            if (w.started_at is not None and w.finished_at is not None
                    and w.started_at <= ts <= w.finished_at):
                return w.case_id
        return ""

    def _nearest_case(self, ts: Optional[datetime]) -> str:
        if ts is None:
            return ""
        best, best_dist = "", None
        for w in self._case_windows:
            if w.started_at is None or w.finished_at is None:
                continue
            if w.started_at <= ts <= w.finished_at:
                return w.case_id
            d = min(abs((ts - w.started_at).total_seconds()),
                    abs((ts - w.finished_at).total_seconds()))
            if best_dist is None or d < best_dist:
                best, best_dist = w.case_id, d
        return best

    # ── 产物落盘（两个独立文件，不碰主 CSV/多维表格）──────────────────
    def _write_products(self, result: AuditResult, audited: list[AuditedEvent]) -> None:
        report_dir = Path(getattr(self._context, "report_dir", "reports"))
        run_id = getattr(self._context, "run_id", "run")
        report_dir.mkdir(parents=True, exist_ok=True)
        json_path = report_dir / f"{run_id}_dlp_event_audit.json"
        csv_path = report_dir / f"{run_id}_unexpected_dlp_events.csv"
        result.audit_json_path = str(json_path)
        result.unexpected_csv_path = str(csv_path)

        payload = {
            "run_id": run_id,
            "status": result.status,
            "reason": result.reason,
            "timeline": {
                "run_started_at": result.run_started_at,
                "actions_finished_at": result.actions_finished_at,
                "event_window_finished_at": result.event_window_finished_at,
                "run_finished_at": result.run_finished_at,
            },
            "summary": {
                "total": result.total, "expected": result.expected,
                "expected_retry": result.expected_retry,
                "ambiguous": result.ambiguous, "unexpected": result.unexpected,
            },
            "expectations": [self._exp_json(e) for e in self._expectations],
            "events": [asdict(a) for a in audited],
        }
        try:
            with json_path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except OSError as e:
            print(f"     ⚠️ 写事件审计 JSON 失败（忽略）：{e}")

        suspicious = [a for a in audited
                      if a.classification in ("ambiguous", "unexpected")]
        try:
            with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["事件时间", "事件UUID", "进程", "文件名", "原始路径",
                            "分类", "分类原因", "当时执行的case", "最近case",
                            "原始日志摘要"])
                for a in suspicious:
                    w.writerow([a.ts, a.event_uuid, a.process_name, a.file_name,
                                a.origin_file_path, a.classification, a.reason,
                                a.case_at, a.nearest_case, a.raw_line])
        except OSError as e:
            print(f"     ⚠️ 写疑似误报 CSV 失败（忽略）：{e}")

    @staticmethod
    def _exp_json(e: _Expectation) -> dict[str, Any]:
        return {"case_id": e.case_id, "kind": e.kind,
                "sensitive_file": e.sensitive_file,
                "started_at": _iso(e.started_at),
                "finished_at": _iso(e.finished_at)}


# ── 模块级纯函数 helper ──────────────────────────────────────────────
def _dedup_by_uuid(events: list[DlpEvent]) -> list[DlpEvent]:
    """按事件 UUID 去重（保序，保留首次）；无 UUID 的事件一律保留。"""
    seen: set[str] = set()
    out: list[DlpEvent] = []
    for ev in events:
        if ev.event_uuid:
            if ev.event_uuid in seen:
                continue
            seen.add(ev.event_uuid)
        out.append(ev)
    return out


def _iso(dt: Optional[datetime]) -> str:
    return dt.isoformat(timespec="seconds") if isinstance(dt, datetime) else ""


def _parse(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
