"""Dump every UI Automation element exposed by Feishu windows.

The script is read-only: it does not focus, click, type into, or close Feishu.
It writes both a log shaped like ``uia-Feishu.log`` and a machine-readable JSON
file.  By default the raw UIA tree is used so elements omitted from the Control
View are retained.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import warnings
from pathlib import Path
from typing import Any, Iterable


# Some Python/comtypes installations try to generate UIA bindings inside the
# read-only site-packages directory.  Put generated bindings in the temp folder
# before importing pywinauto so the script also works in restricted accounts.
import comtypes.client
import comtypes.gen

_COMTYPES_CACHE = Path(tempfile.gettempdir()) / "feishu-uia-comtypes-cache"
_COMTYPES_CACHE.mkdir(parents=True, exist_ok=True)
comtypes.client.gen_dir = os.fspath(_COMTYPES_CACHE)
# Prefer the writable cache over stale generated modules in site-packages.
comtypes.gen.__path__[:] = [os.fspath(_COMTYPES_CACHE)]

warnings.filterwarnings("ignore", message="Revert to STA COM threading mode", category=UserWarning)

import psutil
from pywinauto import Desktop
from pywinauto.uia_defines import IUIA
from pywinauto.uia_element_info import UIAElementInfo


DEFAULT_PROCESS_NAMES = {"feishu.exe", "lark.exe"}


def text_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def log_escape(value: Any) -> str:
    """Make a value safe for a single-quoted, one-line UTF-8 log field."""
    return text_value(value).replace("\\", "\\\\").replace("\r", "\\r").replace("\n", "\\n").replace("'", "\\'")


def safe(getter, default: Any = "") -> Any:
    try:
        value = getter()
        return default if value is None else value
    except Exception:
        return default


def rect_dict(info: UIAElementInfo) -> dict[str, int]:
    rect = safe(lambda: info.rectangle, None)
    if rect is None:
        return {"left": 0, "top": 0, "right": 0, "bottom": 0, "width": 0, "height": 0}
    left, top, right, bottom = int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "width": right - left,
        "height": bottom - top,
    }


def element_record(info: UIAElementInfo, index: int, parent: int | None, depth: int) -> dict[str, Any]:
    raw = info.element
    runtime_id = safe(lambda: list(info.runtime_id), [])
    return {
        "index": index,
        "parent_index": parent,
        "depth": depth,
        "control_type_id": int(safe(lambda: raw.CurrentControlType, 0)),
        "control_type": text_value(safe(lambda: info.control_type)),
        "class_name": text_value(safe(lambda: info.class_name)),
        "name": text_value(safe(lambda: info.name)),
        "automation_id": text_value(safe(lambda: info.automation_id)),
        "framework_id": text_value(safe(lambda: info.framework_id)),
        "process_id": int(safe(lambda: info.process_id, 0)),
        "native_window_handle": int(safe(lambda: info.handle, 0)),
        "runtime_id": runtime_id,
        "rectangle": rect_dict(info),
        "enabled": bool(safe(lambda: info.enabled, False)),
        "offscreen": bool(safe(lambda: raw.CurrentIsOffscreen, False)),
        "is_control_element": bool(safe(lambda: raw.CurrentIsControlElement, False)),
        "is_content_element": bool(safe(lambda: raw.CurrentIsContentElement, False)),
    }


def child_elements(info: UIAElementInfo, view: str) -> list[UIAElementInfo]:
    """Return immediate children using the requested UIA tree view."""
    if view == "raw":
        return info.children(cache_enable=True)

    uia = IUIA().iuia
    walker = uia.ControlViewWalker if view == "control" else uia.ContentViewWalker
    children: list[UIAElementInfo] = []
    child = safe(lambda: walker.GetFirstChildElement(info.element), None)
    while child:
        children.append(UIAElementInfo(child, cache_enable=True))
        child = safe(lambda: walker.GetNextSiblingElement(child), None)
    return children


def dump_tree(
    root: UIAElementInfo,
    view: str,
    max_depth: int,
    max_nodes: int,
) -> tuple[list[dict[str, Any]], list[str], bool]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    truncated = False
    stack: list[tuple[UIAElementInfo, int | None, int]] = [(root, None, 0)]

    while stack:
        if max_nodes and len(records) >= max_nodes:
            truncated = True
            break

        info, parent, depth = stack.pop()
        index = len(records)
        records.append(element_record(info, index, parent, depth))

        if max_depth and depth >= max_depth:
            if safe(lambda: bool(child_elements(info, view)), False):
                truncated = True
            continue

        try:
            children = child_elements(info, view)
        except Exception as exc:
            errors.append(f"node {index}: {type(exc).__name__}: {exc}")
            continue

        # Reverse because the traversal stack is LIFO; output remains in UIA order.
        for child in reversed(children):
            stack.append((child, index, depth + 1))

    return records, errors, truncated


def process_ids(names: set[str], explicit_pids: Iterable[int]) -> set[int]:
    pids = {int(pid) for pid in explicit_pids}
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if (proc.info.get("name") or "").lower() in names:
                pids.add(int(proc.info["pid"]))
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass
    return pids


def find_roots(args: argparse.Namespace) -> list[UIAElementInfo]:
    if args.hwnd:
        return [UIAElementInfo(int(args.hwnd, 0), cache_enable=True)]

    names = DEFAULT_PROCESS_NAMES | {name.lower() for name in args.process}
    pids = process_ids(names, args.pid)
    title_filter = args.title.casefold() if args.title else ""
    roots: list[UIAElementInfo] = []

    for window in Desktop(backend="uia").windows():
        info = window.element_info
        pid = int(safe(lambda: info.process_id, 0))
        title = text_value(safe(lambda: info.name))
        if pid not in pids:
            continue
        if title_filter and title_filter not in title.casefold():
            continue
        roots.append(info)
    return roots


def log_line(record: dict[str, Any]) -> str:
    rect = record["rectangle"]
    indent = "  " * record["depth"]
    return (
        f"{indent}D{record['depth']} CT={record['control_type_id']} "
        f"Type='{log_escape(record['control_type'])}' Class='{log_escape(record['class_name'])}' "
        f"Name='{log_escape(record['name'])}' Aid='{log_escape(record['automation_id'])}' "
        f"Rect='{rect['left']},{rect['top']},{rect['right']},{rect['bottom']} "
        f"{rect['width']}x{rect['height']}' PID={record['process_id']} "
        f"HWND=0x{record['native_window_handle']:X}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导出飞书窗口的全部 Windows UIA 元素（只读）")
    parser.add_argument("--out", type=Path, default=Path("feishu_uia_dump.json"), help="JSON 输出路径")
    parser.add_argument("--log", type=Path, default=Path("feishu_uia_dump.log"), help="文本日志输出路径")
    parser.add_argument("--process", action="append", default=[], help="追加进程名，可重复指定")
    parser.add_argument("--pid", action="append", type=int, default=[], help="追加进程 PID，可重复指定")
    parser.add_argument("--hwnd", help="只导出指定窗口句柄，支持十进制或 0x 十六进制")
    parser.add_argument("--title", default="", help="只导出标题包含该文本的飞书窗口")
    parser.add_argument(
        "--view",
        choices=("raw", "control", "content"),
        default="raw",
        help="UIA 树视图；raw 最完整（默认）",
    )
    parser.add_argument("--max-depth", type=int, default=0, help="最大深度；0 表示不限制")
    parser.add_argument("--max-nodes", type=int, default=0, help="每个窗口最大元素数；0 表示不限制")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_depth < 0 or args.max_nodes < 0:
        print("--max-depth 和 --max-nodes 不能为负数", file=sys.stderr)
        return 2

    roots = find_roots(args)
    if not roots:
        print(
            "没有找到飞书 UIA 顶层窗口。请确认飞书已启动；也可用 --pid、--hwnd 或 --process 指定目标。",
            file=sys.stderr,
        )
        return 1

    created_at = time.strftime("%Y-%m-%d %H:%M:%S")
    output: dict[str, Any] = {
        "created_at": created_at,
        "backend": "uia",
        "view": args.view,
        "read_only": True,
        "windows": [],
    }
    lines = [
        f"[{created_at}] [FeishuUiaDump][UIA] dump begin: view={args.view}, "
        f"windows={len(roots)}, maxDepth={args.max_depth or 'unlimited'}, "
        f"maxNodes={args.max_nodes or 'unlimited'}"
    ]

    total = 0
    for window_index, root in enumerate(roots):
        records, errors, truncated = dump_tree(root, args.view, args.max_depth, args.max_nodes)
        total += len(records)
        root_record = records[0]
        lines.append(
            f"[{created_at}] [FeishuUiaDump][UIA] window begin: index={window_index}, "
            f"pid={root_record['process_id']}, hwnd=0x{root_record['native_window_handle']:X}, "
            f"name='{log_escape(root_record['name'])}'"
        )
        lines.extend(log_line(record) for record in records)
        for error in errors:
            lines.append(f"ERROR {error}")
        lines.append(
            f"[{created_at}] [FeishuUiaDump][UIA] window end: index={window_index}, "
            f"nodes={len(records)}, errors={len(errors)}, truncated={int(truncated)}"
        )
        output["windows"].append(
            {
                "window_index": window_index,
                "root": root_record,
                "node_count": len(records),
                "truncated": truncated,
                "errors": errors,
                "elements": records,
            }
        )

    lines.append(f"[{created_at}] [FeishuUiaDump][UIA] dump end: windows={len(roots)}, nodes={total}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    args.log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"已导出 {len(roots)} 个飞书窗口、{total} 个 UIA 元素")
    print(f"JSON: {args.out.resolve()}")
    print(f"日志: {args.log.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
