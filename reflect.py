"""成功轨迹反哺：从一次成功的 ai step 轨迹中提炼可复用经验，
并以「旁挂 hints」形式沉淀，让下次执行同类指令更少步数。

设计（详见对话决策）：
- 只在成功时触发，失败轨迹不沉淀（避免学坏）。
- hints 作为「经验提示」附加到原指令后，不替换原指令（保留 AI 自主性）。
- hints 按平台分区、并镜像 cases/ 目录树存放，避免跨平台经验互相污染：
    cases/.hints/<channel 按点拆成目录>/<platform>/<case 去掉 channel 前缀>.yaml
  例：desktop_app.im.feishu.outbound_file.drag_drop @ windows
      -> cases/.hints/desktop_app/im/windows/feishu.outbound_file.drag_drop.yaml
  同一 step 名在 mac / windows 往往相同（如「搜索并进入…会话」），
  只按 step 名存会串台；按平台建实体子目录可从结构上杜绝。
  yaml 内另存 channel / platform 字段便于自解释。
- optimized_instruction / rationale 仅写入建议报告（.tmp/reflect_report.md），
  供人工 review 后决定是否合并进 case 源码，不自动改源码。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from dlp_auto.llm.prompts import SYSTEM_PROMPT_REFLECT

_HINTS_ROOT = Path("cases/.hints")
_REPORT = Path(".tmp/reflect_report.md")
# 每个 step 最多保留的 hints 条数：只增不减会无限膨胀，过多的空泛经验反而诱导
# 模型反复确认、陷入循环（实测同一步 7 条能过、10 条就死循环）。超限时保留最近的。
_MAX_HINTS_PER_STEP = 5


def _hints_path(case_id: str, channel: str | None, platform: str | None) -> Path:
    """把 case 落到镜像 cases/ 树的按平台分区 yaml 路径。

    - channel（如 desktop_app.im）拆成子目录；
    - 追加 platform 子目录（mac / windows），跨平台经验物理隔离；
    - 文件名用去掉 channel 前缀后的 case 尾段（更短、避免与目录重复）。
    向后兼容：channel / platform 缺失时退化为 _HINTS_ROOT 下的扁平文件。
    """
    if not channel and not platform:
        return _HINTS_ROOT / f"{_safe(case_id)}.yaml"

    parts = [_HINTS_ROOT]
    if channel:
        parts += [_safe(seg) for seg in channel.split(".") if seg]
    if platform:
        parts.append(_safe(platform))

    leaf = case_id
    if channel and case_id.startswith(channel + "."):
        leaf = case_id[len(channel) + 1:]
    return Path(*parts) / f"{_safe(leaf)}.yaml"


@dataclass
class Reflection:
    hints: list[str]
    optimized_instruction: str
    rationale: str


def load_hints(case_id: str, step_name: str, *,
               channel: str | None = None,
               platform: str | None = None) -> list[str]:
    """读取某 case 某 step 已沉淀的 hints；无则返回空列表。

    channel / platform 决定按平台分区的存放路径（见 _hints_path）；
    缺省时退化为旧的扁平路径，保持向后兼容。
    """
    data = _read_yaml(_hints_path(case_id, channel, platform))
    steps = data.get("steps", {}) if isinstance(data, dict) else {}
    entry = steps.get(step_name)
    if isinstance(entry, dict):
        hints = entry.get("hints")
        return [str(h) for h in hints] if isinstance(hints, list) else []
    return []


class Reflector:
    """封装一次反思 LLM 调用 + hints 沉淀 + 建议报告。"""

    def __init__(self, llm: Any):
        self.llm = llm

    def reflect(self, *, case_id: str, step_name: str, instruction: str,
                trajectory: list, steps: int,
                channel: str | None = None,
                platform: str | None = None) -> Optional[Reflection]:
        traj_text = self._format_trajectory(trajectory)
        user = (f"原始指令：\n{instruction}\n\n"
                f"实际步数：{steps}\n\n"
                f"执行轨迹：\n{traj_text}")
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_REFLECT},
            {"role": "user", "content": user},
        ]
        raw = self.llm.chat(messages, max_tokens=600)
        print(f"     🧠 反哺模型返回：{(raw or '').strip()}")
        ref = self._parse(raw)
        if ref is None:
            return None
        # 防御：模型若无视约束、把原指令原样复读为"改写建议"，归一化为空
        if _norm(ref.optimized_instruction) == _norm(instruction):
            ref.optimized_instruction = ""
        if ref.hints:
            self._persist_hints(case_id, step_name, instruction, steps, ref,
                                channel=channel, platform=platform)
        self._append_report(case_id, step_name, instruction, steps, ref,
                            platform=platform)
        return ref

    # ── 内部 ────────────────────────────────────────────────────────
    @staticmethod
    def _format_trajectory(trajectory: list) -> str:
        lines = []
        for rec in trajectory:
            step = getattr(rec, "step", "?")
            action = getattr(rec, "action", rec)
            obs = getattr(rec, "observation", "")
            lines.append(f"  [{step}] {action} -> {obs}")
        return "\n".join(lines) if lines else "  (空)"

    @staticmethod
    def _parse(raw: str) -> Optional[Reflection]:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\n?|```$", "", text).strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
        if not isinstance(obj, dict):
            return None
        hints = obj.get("hints") or []
        if not isinstance(hints, list):
            hints = []
        return Reflection(
            hints=[str(h) for h in hints],
            optimized_instruction=str(obj.get("optimized_instruction", "")),
            rationale=str(obj.get("rationale", "")),
        )

    def _persist_hints(self, case_id: str, step_name: str, instruction: str,
                       steps: int, ref: Reflection, *,
                       channel: str | None = None,
                       platform: str | None = None) -> None:
        path = _hints_path(case_id, channel, platform)
        data = _read_yaml(path)
        if not isinstance(data, dict):
            data = {}
        data.setdefault("case_id", case_id)
        if channel:
            data["channel"] = channel
        if platform:
            data["platform"] = platform
        steps_map = data.setdefault("steps", {})
        merged = _merge_unique(
            (steps_map.get(step_name) or {}).get("hints", []), ref.hints)
        # 保留最近的若干条，超限从头截断（旧的先淘汰），避免 hints 无限膨胀。
        if len(merged) > _MAX_HINTS_PER_STEP:
            merged = merged[-_MAX_HINTS_PER_STEP:]
        steps_map[step_name] = {
            "hints": merged,
            "last_steps": steps,
            "updated_at": _now(),
        }
        _write_yaml(path, data)
        print(f"     🧠 已沉淀 {len(ref.hints)} 条经验（累计 {len(merged)} 条）"
              f" -> {path}")

    def _append_report(self, case_id: str, step_name: str, instruction: str,
                       steps: int, ref: Reflection, *,
                       platform: str | None = None) -> None:
        _REPORT.parent.mkdir(parents=True, exist_ok=True)
        suggest = (f"\n  > {ref.optimized_instruction}"
                   if ref.optimized_instruction.strip()
                   else " （无，指令已足够高效）")
        plat_tag = f" | {platform}" if platform else ""
        block = (
            f"\n## {_now()} | {case_id}{plat_tag} | {step_name}\n"
            f"- 实际步数：{steps}\n"
            f"- hints：{ref.hints if ref.hints else '（无）'}\n"
            f"- 指令改写建议：{suggest}\n"
            f"- 理由：{ref.rationale}\n"
            f"- 原指令：\n  > {instruction}\n"
        )
        with _REPORT.open("a", encoding="utf-8") as f:
            f.write(block)
        print(f"     📝 反思建议已写入 {_REPORT}")


# ── yaml / 工具 ────────────────────────────────────────────────────────
def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    import yaml  # type: ignore
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _write_yaml(path: Path, data: dict) -> None:
    import yaml  # type: ignore
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def _merge_unique(old: list, new: list) -> list:
    seen, out = set(), []
    for h in list(old) + list(new):
        s = str(h)
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _safe(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]", "_", name)


def _norm(text: str) -> str:
    """归一化文本用于比较：去首尾空白、压缩内部空白。"""
    return re.sub(r"\s+", "", str(text))


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
