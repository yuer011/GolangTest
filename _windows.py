"""Windows corplink DLP 客户端日志验证后端。

流程（详见 docs/dlp_client_log_verify_design.md §3）：
1. on_case_start：记录本 case 的时间窗起点 window_start（本地时钟）。
2. check：
   - 调解密器 `decoder <加密日志> <明文临时文件>` 全量解密（实测能直读被独占锁定的原文件，~130ms）。
   - 只保留「行首时间戳 ≥ window_start」且「含 event_marker + 事件UUID」的**真事件**行，
     锚定真正的事件发射源，规避把宿主 shell 回显（ndlp_svc_mgr.cpp on websocket msg）误当事件。
   - 文件类 case（rep.sensitive_file 有值）：origin file path 含本次唯一文件名 → 命中。
     截图类 case（sensitive_file 为空）：origin file path 扩展名 ∈ image_exts → 命中（进程名不参与匹配）。
   - 首轮未命中：按 settle_wait_sec 等一次、重解一次再判（事件落盘可能晚几秒）。
   - 轮转兜底：当前文件最早时间戳已晚于 window_start → 追加解密 rotated_globs 一起过滤。
   - 命中后提取 uuid / process name / origin file path / 整条行，回填 rep 与 evidence。
   - 用完删除临时明文。

零副作用（硬约束 #6）：解密器/路径缺失、解密失败、读不到 → inconclusive，不打断 run、不 fake pass。
"""
from __future__ import annotations

import os
import re
import subprocess
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from ..outcome import CheckContext, CheckOutcome
from ._base import DlpEvent, EventCollectError, parse_event_line, parse_line_ts

# 时间窗起点小幅回拨：防止 on_case_start 与真实外发之间、以及 ms/us 取整的边界抖动
# 造成事件被判在窗外。取 2s——远小于单条 case 时长，不会跨到上一条 case 的事件。
_WINDOW_GUARD_SEC = 2
_NAME = "dlp_log"

# 真实事件行「行首锚」：corplink 会把宿主(Trae)的 shell I/O 也记进同一日志，
# 其 ndlp_svc_mgr.cpp:643 on websocket msg 行的 JSON 里**照抄了真实事件行的全文**
# （含 dlp_event_upload_handler.cpp + 事件UUID 字样）。若用「行内含 marker」的宽匹配，
# 会把这些回显行也当成事件（实测踩坑）。故要求 marker 必须出现在**日志源位置字段**——
# 即 [时间] [pid:tid] [default] [级别] 之后紧跟的 `<marker>:<行号>`，回显行该位置是
# ndlp_svc_mgr.cpp，天然被排除。<marker> 由调用方传入并在此转义。
def _build_event_head_re(marker: str) -> "re.Pattern[str]":
    return re.compile(
        r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?\]\s+"  # [时间戳]
        r"\[[^\]]*\]\s+\[[^\]]*\]\s+\[[^\]]*\]\s+"                # [pid:tid][default][级别]
        + re.escape(marker) + r":\d+\s")                          # marker:行号（源位置字段）


class WindowsCorplinkBackend:
    name = _NAME
    scope = "case"

    def __init__(self, *, path: str | None, decoder: str | None,
                 event_marker: str = "dlp_event_upload_handler.cpp",
                 image_exts: list[str] | None = None,
                 settle_wait_sec: float = 5.0,
                 settle_retries: int = 3,
                 rotated_globs: list[str] | None = None,
                 tmp_dir: str = ".tmp/dlp_decoded"):
        self.path = Path(path).expanduser() if path else None
        self.decoder = Path(decoder).expanduser() if decoder else None
        self.event_marker = event_marker or "dlp_event_upload_handler.cpp"
        self._event_head_re = _build_event_head_re(self.event_marker)
        self.image_exts = [e.lower() for e in (image_exts or
                           [".png", ".jpg", ".jpeg", ".bmp", ".gif"])]
        self.settle_wait_sec = float(settle_wait_sec or 0)
        # 首轮未命中后，最多再「等 settle_wait_sec → 重查」几轮（命中即早退）。
        # DLP 事件落盘有延迟（实测某些客户端十几秒才落盘），一次等太久浪费所有命中的
        # case、等太短又会假 failed；故用「短等待 + 多轮重试、命中即停」平衡。
        self.settle_retries = max(0, int(settle_retries))
        self.rotated_globs = list(rotated_globs or [])
        self.tmp_dir = Path(tmp_dir)

    # ── 时间窗起点：case 动作开始前记一次 ──────────────────────────────
    def on_case_start(self, ctx: CheckContext) -> None:
        start = datetime.now() - timedelta(seconds=_WINDOW_GUARD_SEC)
        ctx.extras["dlp_log_window_start"] = start

    # ── 主判定 ────────────────────────────────────────────────────────
    def check(self, ctx: CheckContext) -> CheckOutcome:
        # 配置完整性（零猜测）：缺路径/解密器一律 inconclusive 并提示补哪项
        if self.path is None:
            return CheckOutcome(
                self.name, "inconclusive",
                "未配置 Windows DLP 日志路径（verify.dlp_log.windows.path），无法检索。")
        if self.decoder is None:
            return CheckOutcome(
                self.name, "inconclusive",
                "未配置 DLP 日志解密器（verify.dlp_log.windows.decoder），"
                "加密日志无法解密。请补解密器可执行文件路径。")
        if not self.decoder.exists():
            return CheckOutcome(
                self.name, "inconclusive",
                f"DLP 日志解密器不存在：{self.decoder}")
        if not self.path.exists():
            return CheckOutcome(
                self.name, "inconclusive",
                f"DLP 日志文件不存在：{self.path}", {"path": str(self.path)})

        window_start = ctx.extras.get("dlp_log_window_start")
        if not isinstance(window_start, datetime):
            # on_case_start 未跑（异常路径）：退化为「不做时间窗过滤」，避免误判
            window_start = None

        rep = getattr(ctx, "rep", None)
        sensitive_file = (getattr(rep, "sensitive_file", "") or "").strip()

        # 首轮判定；未命中且配了重试 → 「等 settle_wait_sec → 重查」，最多 settle_retries 轮，
        # 命中即早退（事件落盘延迟兜底：某些 DLP 客户端事件要十几秒才落盘，见 LESSONS #15）。
        outcome = self._scan_and_judge(ctx, window_start, sensitive_file)
        if outcome.status == "failed" and self.settle_wait_sec > 0:
            for attempt in range(1, self.settle_retries + 1):
                print(f"  ⏳ DLP 日志未命中，等 {self.settle_wait_sec}s 后重查"
                      f"（第 {attempt}/{self.settle_retries} 轮，事件落盘可能有延迟）")
                time.sleep(self.settle_wait_sec)
                retry = self._scan_and_judge(ctx, window_start, sensitive_file)
                outcome = retry
                if retry.status == "passed":
                    return retry
        return outcome

    # ── 旁路事件审计：只读收集时间窗内全部真事件（RunEventAuditor 专用）──
    def collect_events(self, window_start, window_end) -> list[DlpEvent]:
        """收集 [window_start, window_end] 内的**全部**真实外发事件（含轮转），按时间升序。

        复用 case 级既有「全量解密 → 行首锚 marker → 下界过滤」逻辑，仅额外做 window_end
        上界过滤。配置缺失 / 解密失败一律抛 EventCollectError，交由审计器降级为
        `inconclusive`（不冒充干净，硬约束 #10）；本方法不改任何 rep、不写盘、纯只读。
        """
        if self.path is None:
            raise EventCollectError(
                "未配置 Windows DLP 日志路径（verify.dlp_log.windows.path），无法扫描事件。")
        if self.decoder is None:
            raise EventCollectError(
                "未配置 DLP 日志解密器（verify.dlp_log.windows.decoder），加密日志无法解密。")
        if not self.decoder.exists():
            raise EventCollectError(f"DLP 日志解密器不存在：{self.decoder}")
        if not self.path.exists():
            raise EventCollectError(f"DLP 日志文件不存在：{self.path}")

        try:
            events, earliest = self._collect_events(self.path, window_start)
            if (window_start is not None and earliest is not None
                    and earliest > window_start and self.rotated_globs):
                for name in self.rotated_globs:
                    rp = self.path.parent / name
                    if not rp.exists():
                        continue
                    try:
                        ev2, _ = self._collect_events(rp, window_start)
                    except _DecodeError:
                        continue
                    events.extend(ev2)
        except _DecodeError as e:
            raise EventCollectError(str(e)) from e

        # 管理汇总行过滤（仅审计路径）：同一个 event_marker（dlp_event_upload_handler.cpp）
        # 除了打「单条外发事件」，还会打「批量上传」管理型汇总行——真机实测同一 marker 3554
        # 行里仅 1 行是真事件，其余 3553 行是 `start upload dlp event, size:N` /
        # `upload dlp batch, db loaded:...` / `associate tag size:N`，全都**既无事件UUID
        # 也无 origin file path**。case 级 check() 靠 _match(origin_file_path) 天然滤掉它们，
        # 但审计的兜底规则会把它们全判成 unexpected（疑似误报），淹没真实产物。故此处只保留
        # 「至少有事件UUID 或 origin file path 之一」的行——这正是能被任一归类规则消费的信息，
        # 两者皆空的行对审计无任何信息量，安全丢弃（不碰 case 级共用的 _collect_events）。
        events = [e for e in events if e.event_uuid or e.origin_file_path]
        # 上界过滤：窗口右边界之后的事件（如服务端回查期间的后台事件）不纳入本 run 审计。
        if window_end is not None:
            events = [e for e in events if e.ts is None or e.ts <= window_end]
        events.sort(key=lambda e: (e.ts is None, e.ts or datetime.min))
        return events

    # ── 一轮：解密 → 时间窗过滤 → 匹配 → 判定 ─────────────────────────
    def _scan_and_judge(self, ctx: CheckContext, window_start,
                        sensitive_file: str) -> CheckOutcome:
        try:
            events, earliest = self._collect_events(self.path, window_start)
        except _DecodeError as e:
            return CheckOutcome(self.name, "inconclusive", str(e),
                                {"path": str(self.path)})

        # 轮转兜底：当前文件最早时间戳已晚于窗起点 → 期间轮转过，追加解已轮转文件
        rotated_scanned = []
        if (window_start is not None and earliest is not None
                and earliest > window_start and self.rotated_globs):
            for name in self.rotated_globs:
                rp = self.path.parent / name
                if not rp.exists():
                    continue
                try:
                    ev2, _ = self._collect_events(rp, window_start)
                except _DecodeError:
                    continue
                events.extend(ev2)
                rotated_scanned.append(str(rp))

        hit = self._match(events, sensitive_file)
        if hit is not None:
            self._fill_report(ctx, hit)
            kind = "文件名" if sensitive_file else "文件类型(图片)"
            return CheckOutcome(
                self.name, "passed",
                f"DLP 日志命中本次外发事件（按{kind}匹配）：process={hit.process_name} "
                f"file={hit.origin_file_path}",
                self._evidence(hit, window_start, rotated_scanned))

        # 时间窗内无匹配事件 → failed
        expect = (f"文件名含「{sensitive_file}」" if sensitive_file
                  else f"文件类型为图片（{'/'.join(self.image_exts)}）")
        return CheckOutcome(
            self.name, "failed",
            f"DLP 日志时间窗内未发现本次外发事件（期望：{expect}；"
            f"窗内共解析到 {len(events)} 条真实事件）。",
            {"path": str(self.path),
             "window_start": window_start.isoformat() if window_start else None,
             "events_in_window": len(events),
             "rotated_scanned": rotated_scanned})

    # ── 解密单个日志文件并抽取「时间窗内真事件」 ──────────────────────
    def _collect_events(self, src: Path, window_start):
        """返回 (窗内真事件列表, 该文件最早可解析时间戳)。解密失败抛 _DecodeError。"""
        dst = self._decode(src)
        earliest = None
        events: list[DlpEvent] = []
        try:
            with dst.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    ts = parse_line_ts(line)
                    if ts is not None and (earliest is None or ts < earliest):
                        earliest = ts
                    # 锚定真正的事件发射源：marker 必须出现在**日志源位置字段**（行首锚），
                    # 而非行内任意位置——否则会把宿主 shell 回显（其 JSON 里照抄了事件全文）
                    # 误当事件。宿主回显行该位置是 ndlp_svc_mgr.cpp，被行首锚天然排除。
                    if not self._event_head_re.match(line):
                        continue
                    if window_start is not None and (ts is None or ts < window_start):
                        continue
                    events.append(parse_event_line(line))
        finally:
            self._cleanup(dst)
        return events, earliest

    def _match(self, events: list[DlpEvent], sensitive_file: str):
        """按 case 类型选出本次外发事件；取时间窗内最后一条匹配（最贴近本次动作）。"""
        for ev in reversed(events):
            path = ev.origin_file_path or ""
            if sensitive_file:
                if sensitive_file in path:          # 文件类：唯一文件名命中
                    return ev
            else:
                low = path.lower()                  # 截图类：文件类型是图片即可
                if any(low.endswith(ext) for ext in self.image_exts):
                    return ev
        return None

    # ── 解密器调用 ────────────────────────────────────────────────────
    def _decode(self, src: Path) -> Path:
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        dst = self.tmp_dir / f"decode_{src.stem}_{uuid.uuid4().hex[:8]}.log"
        try:
            proc = subprocess.run(
                [str(self.decoder), str(src), str(dst)],
                capture_output=True, timeout=60)
        except FileNotFoundError as e:
            raise _DecodeError(f"调用 DLP 日志解密器失败（未找到）：{e}") from e
        except subprocess.TimeoutExpired as e:
            raise _DecodeError("DLP 日志解密超时（60s）") from e
        if proc.returncode != 0 or not dst.exists():
            tail = (proc.stderr or b"")[-300:].decode("utf-8", errors="replace")
            raise _DecodeError(
                f"DLP 日志解密失败（exit={proc.returncode}）：{tail or '无输出'}")
        return dst

    @staticmethod
    def _cleanup(dst: Path) -> None:
        try:
            if dst.exists():
                dst.unlink()
        except OSError:
            pass

    # ── 回填报告字段 + evidence ───────────────────────────────────────
    @staticmethod
    def _fill_report(ctx: CheckContext, ev: DlpEvent) -> None:
        rep = getattr(ctx, "rep", None)
        if rep is None:
            return
        if hasattr(rep, "dlp_process_name"):
            rep.dlp_process_name = ev.process_name
        if hasattr(rep, "dlp_event_log"):
            rep.dlp_event_log = ev.raw_line
        # 事件UUID 搬进 rep.event_id：供 run 级服务端回查按之精确查询、并落进 CSV。
        # 平台无关字段，Mac 后端命中时也应同样回填（见 server_event 设计稿前提 F）。
        if hasattr(rep, "event_id") and ev.event_uuid:
            rep.event_id = ev.event_uuid

    def _evidence(self, ev: DlpEvent, window_start, rotated_scanned) -> dict:
        return {
            "path": str(self.path),
            "event_uuid": ev.event_uuid,
            "process_name": ev.process_name,
            "origin_file_path": ev.origin_file_path,
            "tag_name": ev.tag_name,
            "hit_line": ev.raw_line[:500],
            "window_start": window_start.isoformat() if window_start else None,
            "rotated_scanned": rotated_scanned,
        }


class _DecodeError(Exception):
    """解密/读取失败的内部信号，统一降级为 inconclusive。"""
