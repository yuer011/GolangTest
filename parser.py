"""模型输出解析：JSON 优先 + 可选文本兜底（迁自 ai-ui/uitars_run.py）。

产出统一的 action dict（供 core/executor.py 消费）：
    {"type": ..., "start": [x,y], "end": [x,y], "key": ..., "content": ..., "direction": ...}

行为（详见 docs/stage2_plan.md §2）：
    raw ─▶ 尝试 json.loads + 字段校验
             ├─ 成功 → 返回 ActionDict
             └─ 失败 ─▶ if fallback_text: 走文本解析；else 抛 ParserError
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

_VALID_TYPES = {
    "click", "left_double", "right_single", "drag",
    "hotkey", "type", "scroll", "wait", "finished", "call_user",
}
_NEED_START = {"click", "left_double", "right_single", "drag", "scroll"}


class ParserError(ValueError):
    pass


def parse_action(raw: str, *, fallback_text: bool = True) -> dict[str, Any]:
    """把模型输出解析成 action dict。"""
    raw = (raw or "").strip()

    action = _try_json(raw)
    if action is not None:
        return _validate(action)

    if fallback_text:
        action = _parse_text(raw)
        if action is not None:
            return _validate(action)

    raise ParserError(f"无法解析模型输出: {raw[:200]!r}")


# 兼容骨架期旧名
def parse_action_json(raw: str) -> dict[str, Any]:
    return parse_action(raw, fallback_text=False)


# ── JSON 路径 ──────────────────────────────────────────────────────────
def _try_json(raw: str) -> Optional[dict[str, Any]]:
    text = _strip_code_fence(raw)
    # 容错：从文本中抽取第一个 {...} 片段
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


# ── 文本路径（兜底，迁自 demo） ─────────────────────────────────────────
def _parse_text(raw: str) -> Optional[dict[str, Any]]:
    text = _extract_action_text(raw)

    for name in ("finished", "call_user", "wait"):
        if re.match(rf"{name}\s*\(", text, re.IGNORECASE):
            return {"type": name}

    m = re.match(
        r"(click|left_double|right_single)\s*\(.*?start_box\s*=\s*['\"]([^'\"]+)['\"]",
        text, re.DOTALL | re.IGNORECASE)
    if m:
        return {"type": m.group(1).lower(), "start": _coords(m.group(2))}

    m = re.match(
        r"drag\s*\(.*?start_box\s*=\s*['\"]([^'\"]+)['\"].*?end_box\s*=\s*['\"]([^'\"]+)['\"]",
        text, re.DOTALL | re.IGNORECASE)
    if m:
        return {"type": "drag", "start": _coords(m.group(1)), "end": _coords(m.group(2))}

    m = re.match(r"hotkey\s*\(\s*key\s*=\s*['\"]([^'\"]+)['\"]\s*\)", text, re.IGNORECASE)
    if m:
        return {"type": "hotkey", "key": m.group(1)}

    m = re.match(r"type\s*\(\s*content\s*=\s*'(.*?)'\s*\)\s*$", text, re.DOTALL | re.IGNORECASE)
    if not m:
        m = re.match(r'type\s*\(\s*content\s*=\s*"(.*?)"\s*\)\s*$', text, re.DOTALL | re.IGNORECASE)
    if m:
        return {"type": "type", "content": m.group(1)}

    m = re.match(
        r"scroll\s*\(.*?start_box\s*=\s*['\"]([^'\"]+)['\"].*?direction\s*=\s*['\"]([^'\"]+)['\"]",
        text, re.DOTALL | re.IGNORECASE)
    if m:
        return {"type": "scroll", "start": _coords(m.group(1)), "direction": m.group(2)}

    return None


def _extract_action_text(text: str) -> str:
    text = _strip_code_fence(text).strip()
    parts = re.split(r"(?i)action\s*:", text)
    return parts[-1].strip() if len(parts) >= 2 else text


def _coords(s: str) -> Optional[list[int]]:
    m = re.search(r"<point>\s*(\d+)\s+(\d+)\s*</point>", s)
    if m:
        return [int(m.group(1)), int(m.group(2))]
    m = re.search(r"\(?\s*(\d+)\s*,\s*(\d+)\s*\)?", s)
    if m:
        return [int(m.group(1)), int(m.group(2))]
    return None


def _strip_code_fence(text: str) -> str:
    return re.sub(r"```[a-zA-Z]*\n?", "", text)


# ── 校验 ────────────────────────────────────────────────────────────────
def _validate(action: dict[str, Any]) -> dict[str, Any]:
    atype = action.get("type")
    if atype not in _VALID_TYPES:
        raise ParserError(f"非法 action type: {atype!r}")

    if atype in _NEED_START:
        start = action.get("start")
        if not _is_xy(start):
            raise ParserError(f"{atype} 缺少合法 start 坐标: {start!r}")
    if atype == "drag" and not _is_xy(action.get("end")):
        raise ParserError(f"drag 缺少合法 end 坐标: {action.get('end')!r}")
    if atype == "hotkey" and not action.get("key"):
        raise ParserError("hotkey 缺少 key")
    if atype == "type" and "content" not in action:
        raise ParserError("type 缺少 content")
    return action


def _is_xy(v: Any) -> bool:
    return (isinstance(v, (list, tuple)) and len(v) == 2
            and all(isinstance(n, (int, float)) for n in v))
