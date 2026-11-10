"""FileWatchResolver：监听本地哨兵文件得到人工反馈（v0.1 骨架占位）。

约定：
    用户在本地写入指定路径文件（如 /tmp/dlp_resume_<correlation_id>.txt），
    内容为 "approve" / "reject"，resolver 读取后返回结果。
"""
from __future__ import annotations

from typing import Any

from .base import HumanResolver, ResumeResult


class FileWatchResolver(HumanResolver):
    name = "file_watch"

    def __init__(self, *, watch_dir: str = "/tmp"):
        self.watch_dir = watch_dir

    def wait(self, payload: Any, timeout_sec: int) -> ResumeResult:
        # correlation_id 从 payload 中取，用于拼哨兵文件名
        raise NotImplementedError("骨架阶段：FileWatchResolver.wait 待实装")

    def cancel(self) -> None:
        # 实装时置 stop Event，让 wait 的轮询循环提前退出
        pass
