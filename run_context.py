"""一次运行共享的配置、平台与产物路径上下文。"""
from __future__ import annotations

import datetime as _dt
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from dlp_auto.config import Settings, load_settings

from .platform import Platform, detect, set_current


@dataclass(frozen=True)
class RunContext:
    """由 CLI 入口创建并贯穿本次运行，避免各组件重复推导运行状态。"""

    run_id: str
    platform: Platform
    settings: Settings
    report_dir: Path
    log_dir: Path
    screenshot_root: Path

    @classmethod
    def create(
        cls,
        *,
        config_path: str | Path = "config/config.yaml",
        report_dir: str | Path = "reports",
        log_dir: str | Path = "logs",
        screenshot_root: str | Path = "screenshots/final",
    ) -> "RunContext":
        settings = load_settings(config_path)
        override = settings.get("platform", "override")
        platform = Platform(override) if override else detect()
        set_current(platform)
        return cls(
            run_id=cls.new_run_id(),
            platform=platform,
            settings=settings,
            report_dir=Path(report_dir),
            log_dir=Path(log_dir),
            screenshot_root=Path(screenshot_root),
        )

    @staticmethod
    def new_run_id() -> str:
        """生成跨进程不可碰撞、仍可按时间排序的运行标识。"""
        now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        return f"{now}_{os.getpid()}_{uuid.uuid4().hex[:8]}"

    @property
    def report_path(self) -> Path:
        return self.report_dir / f"{self.run_id}.csv"

    @property
    def log_path(self) -> Path:
        return self.log_dir / f"run_{self.run_id}.log"

    @property
    def screenshot_dir(self) -> Path:
        return self.screenshot_root / self.run_id

    def screenshot_path(self, case_id: str) -> Path:
        safe_id = case_id.replace("/", "_").replace(" ", "_")
        return self.screenshot_dir / f"{safe_id}.png"
