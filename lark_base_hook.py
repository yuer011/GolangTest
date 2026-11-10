"""LarkBaseHook：把一次运行的报告同步到飞书多维表格（通过本地 lark-cli）。

行为（仅在 run 传入 --lark-base 时被 run.py 注册）：
1. 每次运行新建一张多维表（表名含 run_id，便于区分批次）。
2. 批量写入所有 case 结果记录。
3. 逐个 case 把「末步截图」上传到对应记录的附件列。
4. 打印新建 Base 的可点击链接。

前置条件：
- 本机已安装并登录 lark-cli（`lark-cli auth status` 为 ready）。
- 附件上传要求 `--file` 为当前工作目录内的相对路径，因此截图由
  CaseRunner 落到项目内 `screenshots/final/<case_id>.png`（见 runner）。

任何一步失败都不抛出（由 ReportWriter.fire_hooks 兜底），只打印告警，
不影响 case 运行结果与 CSV 报告。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .schema import CaseReport, RunReport


def _resolve_lark_cli() -> list[str]:
    """解析 lark-cli 的调用前缀（argv 列表）。

    返回 argv 前缀，后续拼上具体子命令参数即可 subprocess 调用。

    **Windows 关键坑（实测）**：npm 全局装的是 `lark-cli.cmd`（批处理包装器）。
    Python subprocess 在 Windows 上跑 `.cmd` 会经由 cmd.exe，**参数里的 `|`、`&`、
    `<`、`>` 等会被 cmd.exe 当成 shell 元字符解析**——我们把整条 DLP 事件日志
    （含 `... | process name is QQ.exe | ...`）作为 `--json` 值传入时，`|` 被当作
    管道符，cmd.exe 试图把 `process` 当命令执行 → 报错 `'process' is not recognized`。
    该 `.cmd` 实为 `node <path>\\run.js %*` 的包装（见其内容），故**优先解析出底层
    run.js，用 `[node, run.js]` 直接调用**，彻底绕开 cmd.exe 的元字符解析。
    解析不到 run.js 时回退到 `.cmd`（无特殊字符的调用仍可用）。

    Mac/Linux：无后缀可执行文件，无 cmd.exe 问题，直接返回其路径。
    """
    if sys.platform != "win32":
        found = shutil.which("lark-cli")
        return [found or "lark-cli"]

    cmd_path = shutil.which("lark-cli.cmd") or shutil.which("lark-cli")
    # 尝试从 .cmd 同目录推导底层 node 脚本，改用 node 直呼以规避 cmd.exe 元字符解析
    if cmd_path:
        base = Path(cmd_path).parent
        run_js = base / "node_modules" / "@larksuite" / "cli" / "scripts" / "run.js"
        if run_js.exists():
            node = shutil.which("node") or "node"
            return [node, str(run_js)]
        return [cmd_path]
    return ["lark-cli.cmd"]


# 结果列（select）候选项，与 writer._STATUS_CN 对齐
_STATUS_CN = {
    "passed": "没有发现问题",
    "failed": "有问题",
    "inconclusive": "未判定",
    "error": "执行异常",
    "skipped": "已跳过",
}
_STATUS_HUE = {
    "没有发现问题": "Green",
    "有问题": "Red",
    "执行异常": "Orange",
    "未判定": "Yellow",
    "已跳过": "Gray",
}
_EXECUTION_CN = {
    "passed": "执行成功",
    "failed": "执行失败",
    "error": "执行异常",
    "skipped": "已跳过",
}
_VERIFY_CN = {
    "passed": "通过",
    "failed": "不通过",
    "inconclusive": "未判定",
    "skipped": "未启用",
}
# 预期策略 / 外发结果的中文映射（与 writer 对齐）
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

# 表字段定义（顺序即列顺序；首列作为主字段）
_FIELDS = [
    {"type": "text", "name": "case_id"},
    {"type": "text", "name": "软件"},
    {"type": "text", "name": "测试场景"},
    {"type": "text", "name": "具体外发动作"},
    {"type": "text", "name": "敏感文件名称"},
    {"type": "text", "name": "平台"},
    {"type": "select", "name": "结果", "multiple": False,
     "options": [{"name": n, "hue": h} for n, h in _STATUS_HUE.items()]},
    {"type": "text", "name": "预期策略"},
    {"type": "text", "name": "执行结果"},
    {"type": "text", "name": "外发结果"},
    {"type": "text", "name": "DLP验收结论"},
    {"type": "text", "name": "进程名称"},
    {"type": "text", "name": "DLP事件日志"},
    {"type": "text", "name": "事件ID"},
    {"type": "text", "name": "问题描述"},
    {"type": "number", "name": "耗时(ms)", "style": {"type": "plain", "precision": 0}},
    {"type": "number", "name": "Token消耗", "style": {"type": "plain", "precision": 0}},
    {"type": "datetime", "name": "运行时间", "style": {"format": "yyyy-MM-dd HH:mm"}},
    {"type": "attachment", "name": "末步截图"},
]
_ATTACH_FIELD = "末步截图"
# 记录写入时的普通列（不含附件，附件走专用命令）
_RECORD_FIELDS = ["case_id", "软件", "测试场景", "具体外发动作", "敏感文件名称", "平台",
                  "结果", "预期策略", "执行结果", "外发结果", "DLP验收结论",
                  "进程名称", "DLP事件日志", "事件ID",
                  "问题描述", "耗时(ms)", "Token消耗", "运行时间"]


class LarkBaseHook:
    name = "lark_base"

    def __init__(self, *, table_name_prefix: str = "DLP自动化测试",
                 cwd: str | None = None, timeout: int = 120):
        self.table_name_prefix = table_name_prefix
        # 附件上传要求相对路径 —— 固定以项目根为 cwd
        self.cwd = cwd or os.getcwd()
        self.timeout = timeout
        # 跨平台解析调用前缀（argv 列表）：Windows 优先 [node, run.js] 绕开 cmd.exe
        # 元字符解析，其它平台为 [lark-cli]。启动时定一次。
        self.cli = _resolve_lark_cli()

    # ── ReportHook 协议 ─────────────────────────────────────────────
    def on_report(self, report: RunReport) -> None:
        print("\n========== 同步飞书多维表格 ==========")
        base_token, table_id, url = self._create_base(report)
        if not base_token:
            return
        print(f"  ✅ 已创建多维表格：{url}")

        record_ids = self._batch_create(base_token, table_id, report.cases,
                                         run_time=self._fmt_time(report.started_at))
        if not record_ids:
            print("  ⚠️ 记录写入失败或为空，跳过截图上传")
            return
        print(f"  ✅ 已写入 {len(record_ids)} 条记录")

        self._upload_shots(base_token, table_id, report.cases, record_ids)
        print(f"  🔗 查看结果：{url}")

    # ── 步骤 1：建表 ────────────────────────────────────────────────
    def _create_base(self, report: RunReport):
        name = f"{self.table_name_prefix} {report.run_id}"
        out = self._run([
            "base", "+base-create", "--name", name,
            "--table-name", "结果", "--fields", json.dumps(_FIELDS, ensure_ascii=False),
        ])
        if out is None:
            return None, None, None
        base = out.get("data", {}).get("base", {})
        table = out.get("data", {}).get("table", {})
        return base.get("base_token"), table.get("id"), base.get("url")

    # ── 步骤 2：批量写记录 ──────────────────────────────────────────
    def _batch_create(self, base_token: str, table_id: str,
                      cases: list[CaseReport], *, run_time: str) -> list[str]:
        rows = [self._case_row(c, run_time) for c in cases]
        if not rows:
            return []
        payload = {"fields": _RECORD_FIELDS, "rows": rows}
        out = self._run([
            "base", "+record-batch-create",
            "--base-token", base_token, "--table-id", table_id,
            "--json", json.dumps(payload, ensure_ascii=False),
        ])
        if out is None:
            return []
        return out.get("data", {}).get("record_id_list", [])

    @staticmethod
    def _case_row(c: CaseReport, run_time: str) -> list:
        return [
            c.id,
            c.app or "-",
            c.scenario or "-",
            c.action or "-",
            c.sensitive_file or "-",
            c.platform,
            _STATUS_CN.get(c.status, c.status),
            _POLICY_CN.get(c.expected_policy or "none", c.expected_policy),
            _EXECUTION_CN.get(c.execution_status, c.execution_status),
            _DELIVERY_CN.get(c.delivery_outcome or "", c.delivery_outcome),
            _VERIFY_CN.get(c.verification_status, c.verification_status),
            c.dlp_process_name or "",
            c.dlp_event_log or "",
            c.event_id or "",
            c.issue or "",
            c.duration_ms or 0,
            c.total_tokens or 0,
            run_time,
        ]

    # ── 步骤 3：逐 case 上传末步截图 ────────────────────────────────
    def _upload_shots(self, base_token: str, table_id: str,
                      cases: list[CaseReport], record_ids: list[str]) -> None:
        uploaded = 0
        for c, rid in zip(cases, record_ids):
            rel = self._rel_shot(c.screenshot)
            if not rel:
                continue
            out = self._run([
                "base", "+record-upload-attachment",
                "--base-token", base_token, "--table-id", table_id,
                "--record-id", rid, "--field-id", _ATTACH_FIELD,
                "--file", rel,
            ])
            if out is not None:
                uploaded += 1
        if uploaded:
            print(f"  ✅ 已上传 {uploaded} 张末步截图")

    def _rel_shot(self, screenshot: str | None) -> str | None:
        """把截图路径规整为 cwd 内的相对路径（lark-cli --file 要求）。"""
        if not screenshot:
            return None
        p = Path(screenshot)
        abs_p = p if p.is_absolute() else (Path(self.cwd) / p)
        if not abs_p.exists():
            print(f"  ⚠️ 截图不存在，跳过：{screenshot}")
            return None
        try:
            rel = abs_p.resolve().relative_to(Path(self.cwd).resolve())
        except ValueError:
            print(f"  ⚠️ 截图不在项目目录内，无法上传：{abs_p}")
            return None
        return f"./{rel.as_posix()}"

    # ── lark-cli 调用封装 ──────────────────────────────────────────
    def _run(self, args: list[str]) -> dict | None:
        cmd = [*self.cli, *args, "--format", "json"]
        try:
            # 不用 text=True：它默认按 UTF-8 解码子进程 stdout，而 Windows 中文环境下
            # lark-cli 可能输出 GBK/OEM 字节（如本地化提示），UTF-8 解不了会在 subprocess
            # 读取线程里抛 UnicodeDecodeError → stdout 变 None → 下游莫名崩溃（见 LESSONS #7）。
            # 改取原始 bytes，自己容错解码，彻底规避编码问题。
            proc = subprocess.run(cmd, cwd=self.cwd, capture_output=True,
                                  timeout=self.timeout)
        except FileNotFoundError:
            print("  ⚠️ 未找到 lark-cli，请先安装并 `lark-cli auth login`")
            return None
        except subprocess.TimeoutExpired:
            print(f"  ⚠️ lark-cli 超时（{self.timeout}s）：{' '.join(args[:2])}")
            return None

        raw = self._decode_bytes(proc.stdout).strip()
        # 部分命令会把进度行打到 stdout 前面，取最后一段 JSON
        out = self._parse_json_tail(raw)
        if out is None:
            err_text = raw or self._decode_bytes(proc.stderr)
            print(f"  ⚠️ lark-cli 返回无法解析（{' '.join(args[:2])}）：\n"
                  f"{err_text[:500]}")
            return None
        if not out.get("ok", False):
            err = out.get("error", {})
            print(f"  ⚠️ lark-cli 执行失败（{' '.join(args[:2])}）："
                  f"{err.get('message', out)}")
            return None
        return out

    @staticmethod
    def _decode_bytes(data) -> str:
        """把子进程原始 bytes 容错解码为 str：UTF-8 优先，回退 GBK，最后 replace 兜底。

        Windows 中文环境下 lark-cli 的输出编码不确定（UTF-8 JSON 主体里可能混入
        GBK 本地化文案），任一单一编码都可能崩。分层尝试保证不抛异常（见 LESSONS #7）。
        """
        if data is None:
            return ""
        if isinstance(data, str):
            return data
        for enc in ("utf-8", "gbk"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    @staticmethod
    def _parse_json_tail(raw: str) -> dict | None:
        if not raw:
            return None
        # 直接可解析
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # 从最后一个 '{' 起尝试（跳过前置进度日志）
        idx = raw.rfind("\n{")
        if idx != -1:
            try:
                return json.loads(raw[idx + 1:])
            except json.JSONDecodeError:
                return None
        return None

    @staticmethod
    def _fmt_time(started_at: str) -> str:
        """ISO(2026-07-22T18:00:00) -> lark 接受的 2026-07-22 18:00:00。"""
        if started_at and "T" in started_at:
            return started_at.replace("T", " ")
        return started_at or ""
