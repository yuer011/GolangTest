"""Mac corplink DLP 客户端日志验证后端。

流程：
1. on_case_start 记录本 case 的明文时间窗起点。
2. check 通过 ``sudo -n cat <加密日志> | bread -`` 解密到 stdout，
   不落明文临时文件。
3. 只解析时间窗内以配置 marker 锚定的 ``dlp audit event`` JSON。
4. 文件 case 按唯一文件名匹配；截图 case 按图片扩展名匹配。
5. 命中后回填 eventId、appLeak.appName 和原始事件行。

``leakFileActions`` 尚未完成真机标定，本后端不据此猜测 audit/block。当前样本只
能证明 audit 事件；block 命中时仍回填 eventId，但本地日志结论保持 inconclusive。

零副作用：配置缺失、sudo 未预授权、解密失败、JSON 无法解析均降级为
``inconclusive`` 或“未命中”，不打断 run、不 fake pass。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from ..outcome import CheckContext, CheckOutcome
from ._base import DlpEvent, EventCollectError

_NAME = "dlp_log"
_WINDOW_GUARD_SEC = 2
_BREAD_FORMAT = "%d\t%C\t%m"
_MAC_TS_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?"
)


def _normalize_category(value: str) -> str:
    return value.strip().removeprefix("[").removesuffix("]")


def parse_mac_line_ts(line: str) -> Optional[datetime]:
    """解析 bread 默认输出的无方括号纳秒时间戳。"""
    match = _MAC_TS_RE.match(line)
    if not match:
        return None
    try:
        parsed = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    fraction = match.group(2)
    if fraction:
        parsed = parsed.replace(microsecond=int(fraction[:6].ljust(6, "0")))
    return parsed


def parse_mac_event_line(
    line: str,
    event_category: str,
    event_marker: str,
) -> Optional[DlpEvent]:
    """从一条 bread 明文行结构化解析 Mac DLP 事件。

    bread 由本后端固定为 ``%d<TAB>%C<TAB>%m`` 格式。类别必须精确命中配置，
    消息必须以 marker 开头；字段缺失或 eventId 不是合法 UUID 时拒绝该行。
    """
    parts = line.rstrip("\r\n").split("\t", 2)
    if len(parts) != 3:
        return None
    timestamp, category, message = parts
    if _normalize_category(category) != _normalize_category(event_category):
        return None
    if not message.startswith(event_marker):
        return None
    payload = message[len(event_marker):].lstrip()
    try:
        data, _ = json.JSONDecoder().raw_decode(payload)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    event_id = str(data.get("eventId") or "").strip()
    try:
        uuid.UUID(event_id)
    except (ValueError, AttributeError):
        return None

    app_leak = data.get("appLeak")
    if not isinstance(app_leak, dict):
        app_leak = {}
    target_file = data.get("targetFile")
    if not isinstance(target_file, dict):
        target_file = {}

    file_path = str(target_file.get("leakFilePath") or "").strip()
    file_name = str(target_file.get("leakFileName") or "").strip()
    file_extension = str(
        target_file.get("leakFileExtension") or ""
    ).strip()

    return DlpEvent(
        raw_line=line.rstrip("\r\n"),
        ts=parse_mac_line_ts(timestamp),
        event_uuid=event_id,
        process_name=str(app_leak.get("appName") or "").strip(),
        origin_file_path=file_path or file_name,
        tag_name=str(data.get("leakTargetTag") or "").strip(),
        extras={
            "leak_file_name": file_name,
            "leak_file_extension": file_extension,
            "leak_file_content_type": str(
                target_file.get("leakFileContentType") or ""
            ).strip(),
            "leak_type": str(data.get("leakType") or "").strip(),
        },
    )


class MacCorplinkBackend:
    name = _NAME
    scope = "case"

    def __init__(
        self,
        *,
        path: str | None,
        decoder: str | None,
        event_category: str | None,
        event_marker: str | None,
        image_exts: list[str] | None,
        use_sudo: bool = True,
        timeout_sec: float = 60.0,
        settle_wait_sec: float = 5.0,
        settle_retries: int = 3,
    ):
        self.path = Path(path).expanduser() if path else None
        self.decoder = Path(decoder).expanduser() if decoder else None
        self.event_category = (event_category or "").strip()
        self.event_marker = (event_marker or "").strip()
        self.image_exts = [
            str(ext).lower()
            for ext in (image_exts or [])
            if str(ext).strip()
        ]
        self.use_sudo = bool(use_sudo)
        self.timeout_sec = float(timeout_sec or 60.0)
        self.settle_wait_sec = float(settle_wait_sec or 0)
        self.settle_retries = max(0, int(settle_retries))

    def on_case_start(self, ctx: CheckContext) -> None:
        ctx.extras["dlp_log_window_start"] = (
            datetime.now() - timedelta(seconds=_WINDOW_GUARD_SEC)
        )

    def check(self, ctx: CheckContext) -> CheckOutcome:
        missing = self._config_error()
        if missing is not None:
            return missing

        window_start = ctx.extras.get("dlp_log_window_start")
        if not isinstance(window_start, datetime):
            window_start = None

        rep = getattr(ctx, "rep", None)
        sensitive_file = (
            getattr(rep, "sensitive_file", "") or ""
        ).strip()

        outcome = self._scan_and_judge(ctx, window_start, sensitive_file)
        if outcome.status == "failed" and self.settle_wait_sec > 0:
            for attempt in range(1, self.settle_retries + 1):
                print(
                    f"  ⏳ Mac DLP 日志未命中，等 {self.settle_wait_sec}s 后重查"
                    f"（第 {attempt}/{self.settle_retries} 轮，事件落盘可能有延迟）"
                )
                time.sleep(self.settle_wait_sec)
                outcome = self._scan_and_judge(
                    ctx, window_start, sensitive_file
                )
                if outcome.status == "passed":
                    return outcome
        if ctx.policy == "block" and outcome.status == "failed":
            return CheckOutcome(
                self.name,
                "inconclusive",
                "Mac DLP 日志在重试窗口内未找到本次外发事件；"
                "block 策略缺少阻断铁证，不能判定为阻断失败。",
                outcome.evidence,
            )
        return outcome

    # ── 旁路事件审计：只读收集时间窗内全部真事件（RunEventAuditor 专用）──
    def collect_events(self, window_start, window_end) -> list[DlpEvent]:
        """收集 [window_start, window_end] 内的**全部**真实 DLP 事件，按时间升序。

        复用 case 级既有「sudo cat | bread 解密 → marker/category 锚定 → 下界过滤」逻辑，
        仅额外做 window_end 上界过滤。配置缺失 / sudo 未授权 / 解密失败一律抛
        EventCollectError，交审计器降级 `inconclusive`（不冒充干净，硬约束 #10）；
        本方法不改任何 rep、不写明文文件、纯只读。
        """
        missing = self._config_error()
        if missing is not None:
            raise EventCollectError(missing.detail)
        try:
            events = self._collect_events(window_start)
        except _DecodeError as exc:
            raise EventCollectError(str(exc)) from exc
        if window_end is not None:
            events = [e for e in events if e.ts is None or e.ts <= window_end]
        events.sort(key=lambda e: (e.ts is None, e.ts or datetime.min))
        return events

    def _config_error(self) -> Optional[CheckOutcome]:
        if self.path is None:
            return CheckOutcome(
                self.name,
                "inconclusive",
                "未配置 Mac DLP 日志路径（verify.dlp_log.mac.path），无法检索。",
            )
        if self.decoder is None:
            return CheckOutcome(
                self.name,
                "inconclusive",
                "未配置 Mac DLP 日志解密器"
                "（verify.dlp_log.mac.decoder），无法解密。",
            )
        if not self.event_marker:
            return CheckOutcome(
                self.name,
                "inconclusive",
                "未配置 Mac DLP 真实事件锚点"
                "（verify.dlp_log.mac.event_marker），无法识别事件。",
            )
        if not self.event_category:
            return CheckOutcome(
                self.name,
                "inconclusive",
                "未配置 Mac DLP 事件类别"
                "（verify.dlp_log.mac.event_category），无法识别事件。",
            )
        if not self.image_exts:
            return CheckOutcome(
                self.name,
                "inconclusive",
                "未配置 Mac DLP 图片扩展名"
                "（verify.dlp_log.mac.image_exts），无法判断截图事件。",
            )
        if not self.decoder.exists():
            return CheckOutcome(
                self.name,
                "inconclusive",
                f"Mac DLP 日志解密器不存在：{self.decoder}",
            )
        if not os.access(self.decoder, os.X_OK):
            return CheckOutcome(
                self.name,
                "inconclusive",
                f"Mac DLP 日志解密器不可执行：{self.decoder}",
            )
        if not self.path.exists():
            return CheckOutcome(
                self.name,
                "inconclusive",
                f"Mac DLP 日志文件不存在：{self.path}",
                {"path": str(self.path)},
            )
        return None

    def _scan_and_judge(
        self,
        ctx: CheckContext,
        window_start: Optional[datetime],
        sensitive_file: str,
    ) -> CheckOutcome:
        try:
            events = self._collect_events(window_start)
        except _DecodeError as exc:
            return CheckOutcome(
                self.name,
                "inconclusive",
                str(exc),
                {"path": str(self.path)},
            )

        hit = self._match(events, sensitive_file)
        if hit is not None:
            self._fill_report(ctx, hit)
            match_kind = "文件名" if sensitive_file else "文件类型(图片)"
            evidence = self._evidence(hit, window_start)
            if ctx.policy == "block":
                return CheckOutcome(
                    self.name,
                    "inconclusive",
                    "Mac DLP 日志命中本次外发事件并已提取 eventId，"
                    "但现有样本仅标识 dlp audit event，"
                    "leakFileActions 与阻断语义尚未标定，不能作为阻断铁证。",
                    evidence,
                )
            return CheckOutcome(
                self.name,
                "passed",
                f"Mac DLP 日志命中本次外发事件（按{match_kind}匹配）："
                f"app={hit.process_name} file={hit.origin_file_path}",
                evidence,
            )

        expected = (
            f"文件名含「{sensitive_file}」"
            if sensitive_file
            else f"文件类型为图片（{'/'.join(self.image_exts)}）"
        )
        return CheckOutcome(
            self.name,
            "failed",
            f"Mac DLP 日志时间窗内未发现本次外发事件（期望：{expected}；"
            f"窗内共解析到 {len(events)} 条真实事件）。",
            {
                "path": str(self.path),
                "window_start": (
                    window_start.isoformat() if window_start else None
                ),
                "events_in_window": len(events),
            },
        )

    def _collect_events(
        self, window_start: Optional[datetime]
    ) -> list[DlpEvent]:
        plaintext = self._decode_text()
        events: list[DlpEvent] = []
        for line in plaintext.splitlines():
            if self.event_marker not in line:
                continue
            event = parse_mac_event_line(
                line,
                self.event_category,
                self.event_marker,
            )
            if event is None:
                continue
            if (
                window_start is not None
                and (event.ts is None or event.ts < window_start)
            ):
                continue
            events.append(event)
        return events

    def _decode_text(self) -> str:
        decoder = str(self.decoder.resolve())
        if self.use_sudo:
            sudo = shutil.which("sudo")
            if not sudo:
                raise _DecodeError(
                    "未找到 sudo，无法读取 root 权限的 Mac DLP 日志。"
                )
            cat = shutil.which("cat")
            if not cat:
                raise _DecodeError(
                    "未找到 cat，无法读取 root 权限的 Mac DLP 日志。"
                )
            # 只让系统 cat 提权；仓库内 bread 始终以当前用户运行。
            encrypted = self._run_process(
                [sudo, "-n", cat, str(self.path)],
                operation="读取 Mac DLP 加密日志",
                sudo_operation=True,
            )
            return self._run_process(
                [decoder, "-f", _BREAD_FORMAT, "-"],
                operation="Mac DLP 日志解密",
                input_bytes=encrypted,
            ).decode("utf-8", errors="replace")

        return self._run_process(
            [decoder, "-f", _BREAD_FORMAT, str(self.path)],
            operation="Mac DLP 日志解密",
        ).decode("utf-8", errors="replace")

    def _run_process(
        self,
        command: list[str],
        *,
        operation: str,
        input_bytes: bytes | None = None,
        sudo_operation: bool = False,
    ) -> bytes:
        try:
            proc = subprocess.run(
                command,
                input=input_bytes,
                capture_output=True,
                timeout=self.timeout_sec,
                check=False,
            )
        except FileNotFoundError as exc:
            raise _DecodeError(
                f"{operation}失败（未找到可执行文件）：{exc}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise _DecodeError(
                f"{operation}超时（{self.timeout_sec:g}s）"
            ) from exc

        if proc.returncode != 0:
            stderr = (proc.stderr or b"").decode(
                "utf-8", errors="replace"
            ).strip()
            if sudo_operation and (
                "password is required" in stderr.lower()
                or "a terminal is required" in stderr.lower()
                or "not permitted" in stderr.lower()
            ):
                raise _DecodeError(
                    "sudo 未预授权或当前环境禁止提权；请先在运行 case 的终端"
                    "手工执行 sudo -v，再重试。"
                )
            tail = stderr[-300:] if stderr else "无错误输出"
            raise _DecodeError(
                f"{operation}失败（exit={proc.returncode}）：{tail}"
            )
        return proc.stdout or b""

    def _match(
        self, events: list[DlpEvent], sensitive_file: str
    ) -> Optional[DlpEvent]:
        for event in reversed(events):
            path = event.origin_file_path or ""
            file_name = str(
                event.extras.get("leak_file_name") or ""
            )
            if sensitive_file:
                if sensitive_file in path or sensitive_file == file_name:
                    return event
                continue

            extension = str(
                event.extras.get("leak_file_extension") or ""
            ).lower()
            if not extension:
                extension = Path(path).suffix.lower()
            if extension in self.image_exts:
                return event
        return None

    @staticmethod
    def _fill_report(ctx: CheckContext, event: DlpEvent) -> None:
        rep = getattr(ctx, "rep", None)
        if rep is None:
            return
        if hasattr(rep, "dlp_process_name"):
            rep.dlp_process_name = event.process_name
        if hasattr(rep, "dlp_event_log"):
            rep.dlp_event_log = event.raw_line
        if hasattr(rep, "event_id") and event.event_uuid:
            rep.event_id = event.event_uuid

    def _evidence(
        self,
        event: DlpEvent,
        window_start: Optional[datetime],
    ) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "event_id": event.event_uuid,
            "app_name": event.process_name,
            "origin_file_path": event.origin_file_path,
            "leak_file_name": event.extras.get("leak_file_name"),
            "leak_file_extension": event.extras.get(
                "leak_file_extension"
            ),
            "tag_name": event.tag_name,
            "hit_line": event.raw_line[:500],
            "window_start": (
                window_start.isoformat() if window_start else None
            ),
        }


class _DecodeError(Exception):
    """解密/读取失败的内部信号，统一降级为 inconclusive。"""
