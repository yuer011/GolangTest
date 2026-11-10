"""单实例互斥锁：保证同一时刻只有一个 run 进程在真机上操作 GUI。

背景（见 LESSONS.md）：真机 GUI case 单次执行约 50–120 秒，而调用方（终端/AI
执行框架）可能在更短的内部阈值上判定命令"未及时返回"而**自动重试**，于是同一条
命令被启动两次；两个进程并发抢同一个前台窗口与鼠标，互相搅乱截图，轻则各自错峰
侥幸跑完、重则拖拽/点击互相打架导致灾难性重复外发。

对策：进程一启动、在写日志/装配一切之前先抢一把基于文件的锁：
- 用 O_CREAT|O_EXCL 原子创建锁文件，写入本进程 PID + 启动时刻；
- 抢不到（已有活着的持锁进程）→ 立即返回 None，调用方据此**安静退出**，连日志
  都不产生，从根上杜绝并发；
- 若锁文件存在但持有者 PID 已不存在（上次进程崩溃/被强杀留下的陈旧锁）→ 判定为
  stale，接管之；
- 正常结束时删除锁文件；异常退出靠 stale 检测兜底，锁不会永久残留。

解耦：本模块是独立、可整体删除的能力。run 入口默认启用，可用 --no-lock 关闭；
关闭或删除后行为与不引入本能力完全一致（不改变任何 case / 主流程逻辑）。
"""
from __future__ import annotations

import contextlib
import os
from typing import Iterator, Optional


def _pid_alive(pid: int) -> bool:
    """判断给定 PID 的进程是否仍存活（跨平台，只读、无副作用）。"""
    if pid <= 0:
        return False
    if os.name == "nt":
        # Windows：用 tasklist 精确过滤 PID；命中一行含该 PID 即存活。
        # 注意：中文 Windows 的 tasklist 输出是 GBK/OEM 编码，不能用 text=True 的
        # 默认 UTF-8 解码（会 UnicodeDecodeError）。这里取原始 bytes，只判断 PID
        # 数字子串是否出现，用 errors="ignore" 容错解码，规避一切编码问题。
        import subprocess
        try:
            raw = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, timeout=5,
            ).stdout or b""
        except (OSError, subprocess.SubprocessError):
            # 查不了就保守认为存活，避免误删他人锁。
            return True
        out = raw.decode("ascii", errors="ignore")
        return str(pid) in out
    # POSIX：signal 0 探测存在性。
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # 存在但无权限，视为存活
    return True


def _read_lock_pid(path: str) -> Optional[int]:
    """读锁文件里记录的持有者 PID；读不到/格式坏返回 None。"""
    try:
        with open(path, "r", encoding="utf-8") as fp:
            first = fp.readline().strip()
        return int(first) if first else None
    except (OSError, ValueError):
        return None


def _try_create(path: str) -> bool:
    """原子创建锁文件并写入本进程信息；已存在返回 False。"""
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return False
    except OSError:
        # 目录不可写等异常：不因锁失败而阻断主流程，让调用方按"未拿到锁但也没人占"处理。
        return False
    try:
        from datetime import datetime
        os.write(fd, f"{os.getpid()}\n{datetime.now().isoformat()}\n".encode("utf-8"))
    finally:
        os.close(fd)
    return True


@contextlib.contextmanager
def single_instance(lock_path: str) -> Iterator[bool]:
    """上下文管理器：进入时尝试独占锁。

    yield True  →  成功持锁，调用方应继续执行；退出上下文时自动释放。
    yield False →  已有活着的进程持锁，调用方应安静退出、不产生任何副作用。

    用法：
        with single_instance(path) as ok:
            if not ok:
                return 0   # 让路给已在运行的进程
            ...            # 真正的工作
    """
    os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)
    acquired = _try_create(lock_path)

    if not acquired:
        # 锁已存在：检查持有者是否还活着，处理陈旧锁。
        holder = _read_lock_pid(lock_path)
        if holder is not None and _pid_alive(holder):
            # 持有者仍存活（无论是别的 run 还是本进程重入）→ 单实例语义，一律让路。
            yield False
            return
        # 陈旧锁（持有者已死/PID 读不出）→ 接管：删掉重建。
        with contextlib.suppress(OSError):
            os.remove(lock_path)
        acquired = _try_create(lock_path)
        if not acquired:
            # 竞态下被别的进程抢先重建 → 让路，宁可保守。
            yield False
            return

    try:
        yield True
    finally:
        # 只删属于自己的锁（避免误删接管后又被他人重建的锁）。
        if _read_lock_pid(lock_path) == os.getpid():
            with contextlib.suppress(OSError):
                os.remove(lock_path)
