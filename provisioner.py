"""AppProvisioner：app 级、默认关的「环境就绪」保障骨架。

见 docs/app_provisioning_design.md §5。

首要原则（设计 §1.1）——与主流程完全解耦：
    - 可删除：删掉本包 + apps*.yaml + 开关后，主流程与现有 case 照常运行。
    - 可并行：写 case 不依赖本能力；第一阶段人工提前安装/登录。
    - 零侵入：唯一接触点是 CaseRunner 分组循环里一个可选前置钩子，且仅当开关开启才进入。

P2 阶段只落「骨架 + 探测优先 + 失败隔离」的编排，真正的安装（P4）/ 自动登录（P3）留 TODO。
本阶段 auth.mode=manual 的软件：探测未登录时不阻断，仅提示人工登录并放行（第一阶段人工登录）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from dlp_auto.core.platform import Platform

from .catalog import AppCatalog, AppSpec

InstallState = Literal["already", "done", "skipped", "failed"]
LoginState = Literal["already", "done", "skipped", "manual", "failed"]


@dataclass(frozen=True)
class ReadyResult:
    """app 就绪结果；detail 仅人读摘要，严禁包含任何凭据明文（设计 §6）。"""

    app: str
    ok: bool
    installed: InstallState
    logged_in: LoginState
    detail: str = ""


class AppProvisioner:
    """按 app 编排「探测→安装→登录」。默认关：仅当 run.py 显式启用时才被构造与调用。"""

    def __init__(self, catalog: AppCatalog, platform: Platform):
        self.catalog = catalog
        self.platform = platform

    # ── 对外总入口 ────────────────────────────────────────────────
    def ensure_ready(self, app: str) -> ReadyResult:
        spec = self.catalog.get(app)
        if spec is None:
            # 清单未登记：不臆测，直接放行（保持与「未启用」等价，不阻断 case）
            return ReadyResult(app, ok=True, installed="skipped",
                               logged_in="skipped",
                               detail=f"apps.yaml 未登记 {app!r}，跳过就绪检查")

        installed = self._ensure_installed(spec)
        if installed == "failed":
            return ReadyResult(app, ok=False, installed=installed,
                               logged_in="skipped",
                               detail=f"{spec.display_name} 安装未就绪")

        logged_in = self._ensure_logged_in(spec)
        ok = logged_in != "failed"
        return ReadyResult(app, ok=ok, installed=installed, logged_in=logged_in,
                           detail=self._summary(spec, installed, logged_in))

    # ── 安装 ──────────────────────────────────────────────────────
    def _ensure_installed(self, spec: AppSpec) -> InstallState:
        if spec.install.mode == "none":
            return "skipped"
        if self._detect_installed(spec):
            return "already"
        # P4 扩展点：按 spec.install.download[platform] 下载并静默安装。
        # 第一阶段人工安装，故此处不动作，仅报告"未探测到、待人工安装/后续实装"。
        return "skipped"

    def _detect_installed(self, spec: AppSpec) -> bool:
        # TODO(P4)：按 platform 读取 detect 路径并真实探测；当前 TODO 占位一律视为未知→未探测到
        path = spec.install.detect.get(self.platform.value)
        if not path or path == "TODO":
            return False
        from pathlib import Path
        return Path(path).exists()

    # ── 登录 ──────────────────────────────────────────────────────
    def _ensure_logged_in(self, spec: AppSpec) -> LoginState:
        if spec.auth.mode == "none":
            return "skipped"
        if self._detect_logged_in(spec):
            return "already"
        if spec.auth.mode == "manual":
            # 第一阶段：人工提前登录。探测不到也不阻断，交由人工保证。
            return "manual"
        # P3 扩展点：mode=password → AI 导航 + hard step 注入凭据完成登录。
        # 凭据经 self.catalog.credential(spec.auth.credential_ref) 取用，绝不进 AI 指令 / 日志。
        return "manual"

    def _detect_logged_in(self, spec: AppSpec) -> bool:
        # TODO(P3)：用 spec.auth.logged_in_hint + 截图交 AI 判定当前是否已登录。
        # 未配置判定线索或尚未实装 AI 判定 → 一律视为「未探测到已登录」。
        if not spec.auth.logged_in_hint:
            return False
        return False  # P3 接入 AI 判定后在此返回真实结论

    @staticmethod
    def _summary(spec: AppSpec, installed: InstallState, logged_in: LoginState) -> str:
        return f"{spec.display_name}: install={installed}, login={logged_in}"
